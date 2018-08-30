import asyncpg
from collections import deque
# from datetime import datetime
from json.decoder import JSONDecodeError
from os.path import join as pjoin
from tornado import ioloop, web, websocket
from tornado.escape import json_decode, json_encode
# from tornado.queues import Queue, QueueEmpty

from database import setup_database
from utils import genuuid, genhashes, load_config, nested_dd, write_config
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
# resultqueue = None
dbpool = None


def move_to_stale(ipaddress, work):
    global assignedworkcount
    # Not going to catch errors yet for debugging purposes
    del assignedwork[ipaddress][work[0]]
    stalework.append(work)
    assignedworkcount -= 1


class MainHandler(web.RequestHandler):

    def get(self):
        self.write('WoT Console Player Tracker v2 is running!')


class UUIDHandler(web.RequestHandler):

    # @tornado.web.asynchronous
    def get(self):
        self.write(genuuid(self.request.remote_ip))
        # self.write({'uuid': genuuid(self.request.remote_ip)})


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
            print(self.request.body)
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


class WorkHandler(web.RequestHandler):

    def get(self):
        if self.request.remote_ip not in registered:
            # 401 - Not Authorized. Client has not registered yet to work
            self.set_status(401)
            return
        client = self.request.remote_ip
        if len(assignedwork[client]) < server_config['max tasks']:
            # work = workgenerator.next()
            # should we attempt to .pop() anyways and catch the exception?
            if len(stalework) > 0:
                work = stalework.pop()
            else:
                work = next(workgenerator)
            self.write(json_encode(
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
        else:
            # 403 - Forbidden. Too many active tasks
            self.set_status(403)

    def post(self):
        try:
            work = json_decode(self.request.body)
        except JSONDecodeError:
            print(self.request.body)
            self.set_status(400)
        else:
            # TODO: Pass work to a separate database handler
            try:
                # Remove timeout first
                tornado.ioloop.IOLoop.current().remove_timeout(
                    timeouts[self.request.remote_ip][work['batch']]
                )
                del timeouts[self.request.remote_ip][work['batch']]
                del assignedwork[self.request.remote_ip][work['batch']]
                # global batches_complete
                # batches_complete += 1
            except KeyError:
                # 400 - Client Error. Work not assigned to client
                self.set_status(400)


class CancelWorkHandler(web.RequestHandler):

    def get(self, uri=None):
        self.write(uri)
        if not uri:
            # 400 - Client Error. No batch ID set
            self.set_status(400)
        try:
            uri = int(uri)
            if uri not in assignedwork[self.request.remote_ip]:
                raise IndexError
            stalework.append(assignedwork[self.request.remote_ip][uri])
            del assignedwork[self.request.remote_ip][uri]
            ioloop.IOLoop.current().remove_timeout(
                timeouts[self.request.remote_ip][uri]
            )
            del timeouts[self.request.remote_ip][uri]
        except IndexError:
            # 401 - Not Authorized. Client was not assigned this work
            self.set_status(401)


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

    def initialize(self, config):
        self.config = config

    def get(self):
        self.write(json_encode(self.config))

    def post(self):
        registered.add(self.request.remote_ip)


class WorkWSHandler(websocket.WebSocketHandler):
    wschecks = dict()
    wsconns = set()

    async def open(self, *args):
        client = self.request.remote_ip
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

    # Make async if interfacing with database?
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
            print('Server got work from a client that is not found as assigned'
                  ' to its IP')
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
        del results['batch']
        await self.send_work()

        # Dropping to a queue would be faster and prevent blocking future msgs
        # resultqueue.put_nowait(result)

        # Interfacing with a database here would prevent the need to have a
        # dedicated worker that updates rows. However, we would need to be able
        # to send data immediately and return quickly. Looping over 100 items
        # per message may cause the server to hang, plus the method would need
        # to be made async.
        # TODO: Asynchronously update database. asyncpg?
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
        print('Work complete. Shutting down server')
        ioloop.IOLoop.current().stop()
        for conn in WorkWSHandler.wsconns:
            conn.close()

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

            if update:
                if 'debug' in config and config['debug']:
                    print('Updating configuration.')
                    print('Max Xbox account:', max_xbox)
                    print('Max PS4 account:', max_ps4)
                write_config(config, configpath)


def make_app(sfiles, clientconfig):
    return web.Application([
        (r"/", MainHandler),
        (r"/uuid", UUIDHandler),
        (r"/setup", SetupHandler, dict(config=clientconfig)),
        # (r"/updates/([^/]*)", UpdateHandler),
        (r"/updates", UpdateHandler),
        (r"/work", WorkHandler),
        (r"/wswork", WorkWSHandler),
        (r"/cancel/(\d+)", CancelWorkHandler),
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
    agp.add_argument('-p', '--port', help='Port to listen on', default=8888)
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
    args = agp.parse_args()

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
    # resultqueue = Queue()
    # dbpool = asyncpg.create_pool(**server_config['database']['server'])
    # TODO: Create a timer to change startwork
    startwork = True

    try:
        ioloop.IOLoop.current().run_sync(
            lambda: setup_database(server_config['database']))
        ioloop.IOLoop.current().run_sync(
            lambda: opendb(server_config['database']))
        app = make_app(static_files, client_config)
        app.listen(args.port)
        exitcall = ioloop.PeriodicCallback(
            lambda: try_exit(server_config, args.config), 1000)
        exitcall.start()
        ioloop.IOLoop.current().start()
        # ioloop.IOLoop.current().run_sync(
        #     lambda: expand_max_players(server_config, args.config))
    except KeyboardInterrupt:
        print('Shutting down')
        ioloop.IOLoop.current().stop()
        exitcall.stop()
