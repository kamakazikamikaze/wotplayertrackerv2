from asyncpg import create_pool
from collections import deque
from copy import copy
from datetime import datetime
from json.decoder import JSONDecodeError
import linecache
import logging
from os import mkdir, sep
from os.path import join as pjoin
from os.path import split as psplit
from os.path import exists
from pickle import loads, dumps, UnpicklingError
from sys import exit
from tornado import ioloop, web, websocket
from tornado.escape import json_decode, json_encode
import tracemalloc

from database import setup_database
from sendtoindexer import create_generator_diffs, create_generator_players
from sendtoindexer import create_generator_players_sync, send_data
from sendtoindexer import create_generator_totals, _send_to_cluster_skip_errors
from utils import genuuid, genhashes, load_config, nested_dd, write_config
from utils import create_client_config, create_server_config, APIResult, Player
from work import setup_work

workgenerator = None
assignedwork = None
assignedworkcount = 0
timeouts = None
stalework = None
server_config = None
registered = set()
# batches_complete = 0
activedbcallbacks = 0
databasequeue = 0
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
    r"""
    Work that does not return before the timeout is appended to a queue
    """
    global assignedworkcount
    del assignedwork[ipaddress][work[0]]
    stalework.append(work)
    assignedworkcount -= 1


class MainHandler(web.RequestHandler):
    r"""
    Quick running check
    """

    def get(self):
        self.write('WoT Console Player Tracker v2 is running!')


class DebugHandler(web.RequestHandler):
    r"""
    Temporary endpoint until StatusHandler is completed
    """

    def get(self, uri=None):
        if uri is None:
            return
        if uri == 'hashes':
            self.write(json_encode(hashes))
        elif uri == 'work':
            self.write(json_encode(assignedwork))
        # elif uri == 'complete':
        #     self.write(str(batches_complete))
        elif uri == 'queue':
            self.write(str(databasequeue))
        elif uri == 'dbcall':
            self.write(str(activedbcallbacks))
        elif uri == 'registered':
            self.write(str(registered))
        elif uri == 'stale':
            self.write(str(stalework))
        elif uri == 'assignedcount':
            self.write(str(assignedworkcount))
        else:
            self.write('No debug output for: ' + uri)


class UpdateHandler(web.RequestHandler):
    r"""
    Client updates (scripts) as served here
    """

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


class TraceHandler(web.RequestHandler):
    r"""
    View system memory usage and profiling for debugging purposes
    """

    def get(self, uri=None):
        if tracemalloc.is_tracing():
            try:
                uri = 10 if uri is None else int(uri)
            except ValueError:
                uri = 10
            snapshot = tracemalloc.take_snapshot()
            snapshot = snapshot.filter_traces((
                tracemalloc.Filter(False, '<frozen importlib._bootstrap>'),
                tracemalloc.Filter(False, '<unknown>')
            ))
            top_stats = snapshot.statistics('lineno')
            output = []
            for index, stat in enumerate(top_stats[:uri], 1):
                frame = stat.traceback[0]
                filename = sep.join(frame.filename.split(sep)[-2:])
                output.append('#%s: %s:%s: %1.1f KiB<br />' %
                              (index, filename, frame.lineno, stat.size / 1024))
                line = linecache.getline(frame.filename, frame.lineno).strip()
                if line:
                    output.append('&nbsp;&nbsp;&nbsp;&nbsp;%s<br />' % line)
            self.write(
                '<html><body>' +
                ''.join(output) +
                '</body></html>')
        else:
            self.set_status(404)


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
        client = self.request.remote_ip
        # Previously I thought it best to make a local copy of the config so
        # that we do not have a different GET request overwrite the API key.
        # However, this method is not async and is therefore thread-safe. We
        # can overwrite the self.clientconfig for now without any concern.
        # clientconf = copy(self.clientconfig)
        # Immediately assign to catchall
        self.clientconfig['application_id'] = self.serverconfig[
            'application_id']['catchall']
        for key, subdict in self.serverconfig['application_id'].items():
            if key == 'catchall':
                continue
            if client in subdict['addresses']:
                self.clientconfig['application_id'] = subdict['key']
                self.clientconfig['throttle'] = subdict['throttle']
                break
        self.write(json_encode(self.clientconfig))
        WorkWSHandler.maxwork[client] = self.clientconfig[
            'throttle'] + self.serverconfig['extra tasks']

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
    r"""
    Endpoint for delegating work to client machines
    """

    wschecks = dict()
    wsconns = set()
    maxwork = dict()

    def get_compression_options(self):
        # TODO: Read in configuration from server.json
        return {'compression_level': 9}

    async def open(self, *args, **kwargs):
        client = self.request.remote_ip
        if client not in registered:
            self.close()
            return
        logger.info('Worker %s joined', genuuid(client))
        await self.send_work()
        WorkWSHandler.wschecks[client] = ioloop.PeriodicCallback(
            self.send_work, 500)
        WorkWSHandler.wschecks[client].start()
        WorkWSHandler.wsconns.add(self)

    async def send_work(self):
        global workdone
        global assignedworkcount
        if not startwork:
            return
        if workdone:
            self.close()
            return
        client = self.request.remote_ip
        while len(assignedwork[client]) < WorkWSHandler.maxwork[client]:
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
                        logger.info('Work done')
                    return
            await self.write_message(dumps(work), True)
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
        global databasequeue
        # global dbpool
        client = self.request.remote_ip
        try:
            results = loads(message)
            # del message
        except UnpicklingError:
            # Will the clients ever send incomplete data?
            return
        try:
            ioloop.IOLoop.current().remove_timeout(
                timeouts[client][results.batch]
            )
        except AttributeError:
            # Server got work from a client that is not assigned to it. This
            # can occur when a client is running on the same machine as the
            # server, especially if IPv4 and IPv6 is enabled. Avoid using a
            # target of "localhost" to mitigate this.
            return
        # Remove timeout first
        del timeouts[client][results.batch]
        try:
            del assignedwork[client][results.batch]
        except KeyError:
            # work has already been moved to stale. How do we correct this?
            pass
        else:
            # Don't decrement count unless assigned work is removed
            assignedworkcount -= 1
            # global batches_complete
            # batches_complete += 1
        databasequeue += 1
        ioloop.IOLoop.current().add_callback(send_to_database, results)
        del results
        await self.send_work()


async def send_to_elasticsearch(conf):
    r"""
    Send updates to Elasticsearch.

    This method should be called once work has concluded.
    """
    today = datetime.utcnow()
    async with dbpool.acquire() as conn:
        totals = create_generator_totals(
            today,
            await conn.fetch('SELECT * FROM total_battles_{}'.format(
                today.strftime('%Y_%m_%d'))))
        logger.info('ES: Sending totals')
        await send_data(conf, totals)
        diffs = create_generator_diffs(
            today,
            await conn.fetch('SELECT * FROM diff_battles_{}'.format(
                today.strftime('%Y_%m_%d'))))
        logger.info('ES: Sending diffs')
        await send_data(conf, diffs)
        player_ids = set.union(
            set(map(lambda p: int(p['_source']['account_id']), totals)),
            set(map(lambda p: int(p['_source']['account_id']), diffs)))
        stmt = await conn.prepare('SELECT * FROM players WHERE account_id=$1')
        players = create_generator_players(stmt, player_ids)
        logger.info('ES: Sending players')
        await send_data(conf, players, 'update')
        logger.info('ES: Finished')

async def send_everything_to_elasticsearch(conf):
    async with dbpool.acquire() as conn:
        tables = await conn.fetch(
            (
                "SELECT table_name FROM information_schema.tables WHERE "
                "table_schema='public' AND table_type='BASE TABLE'"
            )
        )
        for table in tables:
            logger.info('ES: Sending %s', table['table_name'])
            if 'diff' in table['table_name']:
                diffs = create_generator_diffs(
                    datetime.strptime(
                        table['table_name'],
                        'diff_battles_%Y_%m_%d'),
                    await conn.fetch(
                        'SELECT * from {}'.format(table['table_name'])))
                await send_data(conf, diffs)
            elif 'total' in table['table_name']:
                totals = create_generator_totals(
                    datetime.strptime(
                        table['table_name'],
                        'total_battles_%Y_%m_%d'),
                    await conn.fetch(
                        'SELECT * from {}'.format(table['table_name'])))
                await send_data(conf, totals)
            elif 'players' in table['table_name']:
                players = create_generator_players_sync(
                    await conn.fetch('SELECT * FROM players'))
                await send_data(conf, players)


async def send_missing_players_to_elasticsearch(conf):
    r"""
    Synchronizes players from an existing database to Elasticsearch.

    Only updated players have information sent to ES. If a new cluster
    is added, it will not have all players in it as a result.
    """
    today = datetime.utcnow()
    async with dbpool.acquire() as conn:
        players = [p for p in create_generator_players_sync(
            await conn.fetch('SELECT * FROM players'))]
        for name, cluster in conf['elasticsearch']['clusters'].items():
            await _send_to_cluster_skip_errors(cluster, players)


async def send_to_database(results):
    global activedbcallbacks
    global databasequeue
    activedbcallbacks += 1
    async with dbpool.acquire() as conn:
        # https://stackoverflow.com/a/1109198
        _ = await conn.executemany(
            (
                'SELECT upsert_player($1::int, $2::text, '
                'to_timestamp($3)::timestamp, to_timestamp($4)::timestamp, '
                'to_timestamp($5)::timestamp, $6::int, '
                'to_timestamp($7)::timestamp, $8::text)'
            ),
            tuple((*p, results[1], results[2]) for p in results[0])
        )
    databasequeue -= 1
    activedbcallbacks -= 1


async def opendb(dbconf):
    global dbpool
    dbpool = await create_pool(**dbconf)


async def try_exit(config, configpath):
    if workdone:
        if WorkWSHandler.wsconns:
            for conn in WorkWSHandler.wsconns:
                conn.close()
            # logger.info('Work complete')

        if databasequeue:
            # We still have data to send to the database. Don't exit yet.
            return

        logger.info('Proceeding with post-run cleanup')
        exitcall.stop()
        update = False
        if 'expand' not in config or config['expand']:
            async with dbpool.acquire() as conn:
                maximum = await conn.fetch(
                    (
                        'SELECT MAX(account_id), console FROM '
                        'players GROUP BY console'
                    )
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
                    logger.info('Expanding max player configuration.')
                    logger.debug('Max Xbox account: %i', max_xbox)
                    logger.debug('Max PS4 account: %i', max_ps4)
                    write_config(config, configpath)
        else:
            logger.debug('Not expanding player ID range')

        if 'elasticsearch' in config:
            logger.info('Sending data to Elasticsearch')
            await send_to_elasticsearch(config)

        logger.info('Shutting down server')
        ioloop.IOLoop.current().stop()


def make_app(sfiles, serverconfig, clientconfig):
    return web.Application([
        (r"/", MainHandler),
        (r"/setup", SetupHandler,
         dict(serverconfig=serverconfig, clientconfig=clientconfig)),
        (r"/updates", UpdateHandler),
        (r"/wswork", WorkWSHandler),
        (r"/status", StatusHandler),
        (r"/debug/([^/]*)", DebugHandler),
        (r"/trace/([^/]*)", TraceHandler),
        (r"/files/nix/([^/]*)", web.StaticFileHandler,
         {'path': pjoin(sfiles, 'nix')}),
        (r"/files/win/([^/]*)", web.StaticFileHandler,
         {'path': pjoin(sfiles, 'win')}),
    ])

if __name__ == '__main__':
    from argparse import ArgumentParser
    agp = ArgumentParser()
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
    agp.add_argument(
        '-t',
        '--trace-memory',
        help='Debug memory consumption issues',
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
    if args.trace_memory:
        logger.debug('Starting memory trace')
        tracemalloc.start()

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
        try:
            exitcall.stop()
        except NameError:
            pass
