import asyncpg
from collections import deque
from datetime import datetime
from json.decoder import JSONDecodeError
import logging
from os import mkdir
from os.path import join as pjoin
from os.path import split as psplit
from os.path import exists
from sys import exit
from tornado import ioloop, web, websocket
from tornado.escape import json_decode, json_encode

from database import setup_database
from sendtoindexer import create_generator_diffs, create_generator_players
from sendtoindexer import create_generator_totals, send_data
from utils import genuuid, genhashes, load_config, nested_dd, write_config
from utils import create_client_config, create_server_config
from work import setup_work

workgenerator = None
assignedwork = None
assignedworkcount = 0
timeouts = None
stalework = None
server_config = None
registered = set()
# batches_complete = 0
startwork = False
workdone = False
dbpool = None
logger = logging.getLogger('WoTServer')


def _setupLogging(conf):
    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d | %(name)s | %(levelname)-8s | %(message)s',
        datefmt='%m-%d %H:%M:%S')
    if 'logging' in conf:
        pardir = psplit(conf['logging']['file'])[0]
        if not exists(pardir):
            mkdir(pardir)
        ch = logging.StreamHandler()
        if conf['logging']['level'].lower() == 'debug':
            level = logging.DEBUG
        elif conf['logging']['level'].lower() == 'info':
            level = logging.INFO
        elif conf['logging']['level'].lower() == 'notice':
            level = logging.NOTICE
        elif conf['logging']['level'].lower() == 'warning':
            level = logging.WARNING
        else:
            level = logging.ERROR
        ch.setLevel(level)
        ch.setFormatter(formatter)
        fh = logging.FileHandler(
            datetime.now().strftime(conf['logging']['file']))
        fh.setLevel(level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        logger.addHandler(ch)
        logger.setLevel(level)
    else:
        nu = logging.NullHandler()
        logger.addHandler(nu)
        logger.setLevel(logging.ERROR)


def move_to_stale(ipaddress, work):
    global assignedworkcount
    # Not going to catch errors yet for debugging purposes
    del assignedwork[ipaddress][work[0]]
    stalework.append(work)
    assignedworkcount -= 1


class MainHandler(web.RequestHandler):

    def get(self):
        self.write('WoT Console Player Tracker v2 is running!')


# class UUIDHandler(web.RequestHandler):
#
#     def get(self):
#         self.write(genuuid(self.request.remote_ip))


class DebugHandler(web.RequestHandler):

    def get(self, uri=None):
        if uri == 'hashes':
            self.write(json_encode(hashes))
        elif uri == 'work':
            self.write(json_encode(assignedwork))
        # elif uri == 'complete':
        #     self.write(str(batches_complete))
        elif uri == 'registered':
            self.write(str(registered))
        elif uri == 'stale':
            self.write(str(stalework))
        elif uri == 'assignedcount':
            self.write(str(assignedworkcount))
        else:
            self.write('No debug output for: ' + uri)
        # self.write(str(self.request.uri))


class UpdateHandler(web.RequestHandler):
    r"""
    Client updates (scripts) as served here
    """

    # def get(self, filetype=None):
    # # clientinfo = json_decode(self.request.body)
    # self.write(str(filetype))

    def get(self):
        try:
            client = json_decode(self.request.body)
        except JSONDecodeError:
            self.set_status(400)
        else:
            if client['hash'] == hashes[client['os']][client['filename']]:
                # 204 - No Content. File matches, no updates to pass along
                self.set_status(204)
            else:
                self.redirect(
                    '/files/' +
                    client['os'] +
                    '/' +
                    client['filename'])


class StatusHandler(web.RequestHandler):
    r"""
    Reviewing progress of the current run or connected clients
    """

    def get(self):
        pass


class SetupHandler(web.RequestHandler):
    r"""
    Endpoint for fetching client-side configuration parameters
    """

    def initialize(self, serverconfig, clientconfig):
        self.serverconfig = serverconfig
        self.clientconfig = clientconfig

    def get(self):
        self.write(json_encode(self.clientconfig))

    def post(self):
        if (self.serverconfig['use whitelist'] and
                self.request.remote_ip in self.serverconfig['whitelist']):
            registered.add(self.request.remote_ip)
        elif self.request.remote_ip in self.serverconfig['blacklist']:
            self.set_status(400)
            logger.info(
                'Blacklisted %s attempted to register',
                self.request.remote_ip)
        else:
            registered.add(self.request.remote_ip)


class WorkWSHandler(websocket.WebSocketHandler):
    wschecks = dict()
    wsconns = set()

    def get_compression_options(self):
        # TODO: Read in configuration from server.json
        return {'compression_level': 9}

    async def open(self, *args, **kwargs):
        client = self.request.remote_ip
        if client not in registered:
            self.close()
        logger.info('Worker %s joined', genuuid(client))
        await self.send_work()
        WorkWSHandler.wschecks[client] = ioloop.PeriodicCallback(
            self.send_work, 200)
        WorkWSHandler.wschecks[client].start()
        WorkWSHandler.wsconns.add(self)

    async def send_work(self):
        global workdone
        global assignedworkcount
        if not startwork:
            return
        if workdone:
            self.close()
        client = self.request.remote_ip
        while len(assignedwork[client]) < server_config['max tasks']:
            try:
                work = stalework.pop()
            except IndexError:
                try:
                    work = next(workgenerator)
                    if work is None:
                        raise StopIteration
                except StopIteration:
                    if len(stalework) == 0 and assignedworkcount == 0:
                        workdone = True
                    return
            await self.write_message(json_encode(
                {
                    'batch': work[0],
                    'players': work[1],
                    'realm': work[2]
                }
            ))
            assignedwork[client][work[0]] = work
            timeouts[client][work[0]] = ioloop.IOLoop.current().call_later(
                server_config['timeout'],
                move_to_stale,
                client,
                work
            )
            assignedworkcount += 1

    def on_close(self):
        client = self.request.remote_ip
        WorkWSHandler.wschecks[client].stop()
        del WorkWSHandler.wschecks[client]
        WorkWSHandler.wsconns.remove(self)
        logger.info('Worker %s disconnected', genuuid(client))

    async def on_message(self, message):
        global assignedworkcount
        global dbpool
        client = self.request.remote_ip
        try:
            results = json_decode(message)
        except JSONDecodeError:
            # Will the clients ever send erroneous result formats?
            return
        try:
            ioloop.IOLoop.current().remove_timeout(
                timeouts[client][results['batch']]
            )
        except AttributeError:
            # Server got work from a client that is not assigned to it
            return
        # Remove timeout first
        del timeouts[client][results['batch']]
        try:
            del assignedwork[client][results['batch']]
        except KeyError:
            # work has already been moved to stale. How do we correct this?
            pass
        assignedworkcount -= 1
        # global batches_complete
        # batches_complete += 1
        # results['_last_api_pull'] = datetime.utcfromtimestamp(
        #     results['_last_api_pull'])
        await self.send_work()

        ioloop.IOLoop.current().add_callback(send_to_database, results)


async def send_to_elasticsearch(conf):
    today = datetime.utcnow()
    async with dbpool.acquire() as conn:
        totals = create_generator_totals(
            today,
            await conn.fetch('SELECT * FROM total_battles_{}'.format(
                today.strftime('%Y_%m_%d'))))
        logger.info('ES: Sending totals')
        send_data(conf, totals)
        diffs = create_generator_diffs(
            today,
            await conn.fetch('SELECT * FROM diff_battles_{}'.format(
                today.strftime('%Y_%m_%d'))))
        logger.info('ES: Sending diffs')
        send_data(conf, diffs)
        player_ids = set.union(
            set(map(lambda p: int(p['_source']['account_id']), totals)),
            set(map(lambda p: int(p['_source']['account_id']), diffs)))
        stmt = await conn.prepare('SELECT * FROM players WHERE account_id=$1')
        # Will this work as a generator?
        players = create_generator_players(stmt, player_ids)
        logger.info('ES: Sending players')
        send_data(conf, players, 'update')
        logger.info('ES: Finished')

async def send_everything_to_elasticsearch(conf):
    async with dbpool.acquire() as conn:
        tables = await conn.fetch('SELECT table_name FROM information_schema.tables WHERE table_schema="public" AND table_type="BASE TABLE"')
        for table in tables:
            logger.info('ES: Sending %s', table['table_name'])
            if 'diff' in table['table_name']:
                diffs = create_generator_diffs(
                    datetime.strptime(
                        table,
                        'diff_battles_%Y_%m_%d'),
                    await conn.fetch('SELECT * from $1', table['table_name']))
                send_data(conf, diffs)
            elif 'total' in table['table_name']:
                totals = create_generator_totals(
                    datetime.strptime(
                        table,
                        'total_battles_%Y_%m_%d'),
                    await conn.fetch('SELECT * from $1', table['table_name']))
                send_data(conf, totals)
            elif 'player' in table['table_name']:
                players = create_generator_players(
                    await conn.fetch('SELECT * FROM players'))
                send_data(conf, players, 'update')


async def send_to_database(results):
    # If UPDATE is followed by a 0, the player does not already exist.
    # We will then insert them. Since 99.9% of players should already
    # exist in our DB, this should provide the best performance.
    # Also, the results are a nested dict of {'playerid': {data}, ...}
    # so we will need to efficiently pass this to executemany
    # print(results)
    async with dbpool.acquire() as conn:
        for __, p in results['data'].items():
            if p is None:
                continue
            # print(p)
            res = await conn.execute('''
                UPDATE players SET (last_battle_time, updated_at, battles,
                _last_api_pull) = (to_timestamp($1), to_timestamp($2), $3,
                to_timestamp($4)) WHERE account_id = $5
                ''',
                                     p['last_battle_time'],
                                     p['updated_at'],
                                     p['statistics']['all']['battles'],
                                     results['_last_api_pull'],
                                     p['account_id'])
            if res.split()[-1] == '0':
                res = await conn.execute('''
                    INSERT INTO players (account_id, nickname, console,
                    created_at, last_battle_time, updated_at, battles,
                    _last_api_pull) VALUES
                    ($1, $2, $3, to_timestamp($4), to_timestamp($5),
                    to_timestamp($6), $7, to_timestamp($8))
                ''',
                                         p['account_id'],
                                         p['nickname'],
                                         results['console'],
                                         p['created_at'],
                                         p['last_battle_time'],
                                         p['updated_at'],
                                         p['statistics']['all']['battles'],
                                         results['_last_api_pull'])

async def opendb(dbconf):
    global dbpool
    dbpool = await asyncpg.create_pool(**dbconf)


async def try_exit(config, configpath):
    if workdone:

        for conn in WorkWSHandler.wsconns:
            conn.close()

        exitcall.stop()
        logger.info('Work complete')

        update = False
        async with dbpool.acquire() as conn:
            maximum = await conn.fetch(
                'SELECT MAX(account_id), console FROM players GROUP BY console'
            )
            for record in maximum:
                if record['console'] == 'xbox':
                    max_xbox = record['max']
                else:
                    max_ps4 = record['max']

            if 'max account' not in config['xbox']:
                config['xbox']['max account'] = max_xbox + 200000
                update = True
            elif config['xbox']['max account'] - max_xbox < 50000:
                config['xbox']['max account'] += 100000
                update = True
            if 'max account' not in config['ps4']:
                config['ps4']['max account'] = max_ps4 + 200000
                update = True
            elif config['ps4']['max account'] - max_ps4 < 50000:
                config['ps4']['max account'] += 100000
                update = True

            logger.info('Checking database to expand players')
            if update:
                logger.debug('Updating configuration.')
                logger.debug('Max Xbox account: %i', max_xbox)
                logger.debug('Max PS4 account: %i', max_ps4)
                write_config(config, configpath)

        if 'elasticsearch' in config:
            logger.info('Sending data to Elasticsearch')
            await send_to_elasticsearch(config)

        logger.info('Shutting down server')
        ioloop.IOLoop.current().stop()


def make_app(sfiles, serverconfig, clientconfig):
    return web.Application([
        (r"/", MainHandler),
        # (r"/uuid", UUIDHandler),
        (r"/setup", SetupHandler,
         dict(serverconfig=serverconfig, clientconfig=clientconfig)),
        (r"/updates", UpdateHandler),
        (r"/wswork", WorkWSHandler),
        (r"/status", StatusHandler),
        (r"/debug/([^/]*)", DebugHandler),
        (r"/files/nix/([^/]*)", web.StaticFileHandler,
         {'path': pjoin(sfiles, 'nix')}),
        (r"/files/win/([^/]*)", web.StaticFileHandler,
         {'path': pjoin(sfiles, 'win')}),
    ])

if __name__ == '__main__':
    from argparse import ArgumentParser
    agp = ArgumentParser()
    # agp.add_argument('-p', '--port', help='Port to listen on', default=8888)
    agp.add_argument(
        '-f',
        '--static-files',
        help='Static files to serve',
        default='./files')
    agp.add_argument(
        '-c',
        '--client-config',
        help='Client configuration to use',
        default='./config/client.json')
    agp.add_argument(
        'config',
        help='Server configuration file to use',
        default='./config/server.json')
    agp.add_argument(
        '-g',
        '--generate-config',
        help='Generate first-time configuration',
        default=False,
        action='store_true')
    args = agp.parse_args()

    if args.generate_config:
        create_client_config(args.client_config)
        create_server_config(args.config)
        exit()

    # Reassign arguments
    static_files = args.static_files
    server_config = load_config(args.config)
    client_config = load_config(args.client_config)

    # Setup server
    workgenerator = setup_work(server_config)
    assignedwork = nested_dd()
    timeouts = nested_dd()
    stalework = deque()
    hashes = genhashes(static_files)
    client_config['files'] = list(hashes['win'].keys())
    # TODO: Create a timer to change startwork
    startwork = True
    _setupLogging(server_config)

    try:
        start = datetime.now()
        ioloop.IOLoop.current().run_sync(
            lambda: setup_database(server_config['database']))
        ioloop.IOLoop.current().run_sync(
            lambda: opendb(server_config['database']))
        app = make_app(static_files, server_config, client_config)
        app.listen(server_config['port'])
        exitcall = ioloop.PeriodicCallback(
            lambda: try_exit(server_config, args.config), 1000)
        exitcall.start()
        ioloop.IOLoop.current().start()
        end = datetime.now()
        logger.info('Finished')
        logger.info('Total runtime: %s', end - start)
    except KeyboardInterrupt:
        logger.info('Shutting down')
        ioloop.IOLoop.current().stop()
        exitcall.stop()
