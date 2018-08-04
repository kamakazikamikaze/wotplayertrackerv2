from collections import deque
from json.decoder import JSONDecodeError
from os.path import join as pjoin
from tornado.escape import json_decode, json_encode
import tornado.ioloop
import tornado.web
import tornado.websocket
from utils import genuuid, genhashes, load_config, nested_dd
from work import setup_work

workgenerator = None
assignedwork = None
timeouts = None
stalework = None
server_config = None
registered = set()
# batches_complete = 0
startwork = False

def move_to_stale(ipaddress, work):
    # Not going to catch errors yet for debugging purposes
    del assignedwork[ipaddress][work[0]]
    stalework.append(work)

class MainHandler(tornado.web.RequestHandler):

    def get(self):
        self.write('WoT Console Player Tracker v2 is running!')


class UUIDHandler(tornado.web.RequestHandler):

    # @tornado.web.asynchronous
    def get(self):
        self.write(genuuid(self.request.remote_ip))
        # self.write({'uuid': genuuid(self.request.remote_ip)})


class DebugHandler(tornado.web.RequestHandler):

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
        else:
            self.write('No debug output for: ' + uri)
        # self.write(str(self.request.uri))


class UpdateHandler(tornado.web.RequestHandler):
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
                # with open('./files/' + client['os'] + '/' + client['filename']) as f:
                #     self.write(f.readlines())
                self.redirect(
                    '/files/' +
                    client['os'] +
                    '/' +
                    client['filename'])


class WorkHandler(tornado.web.RequestHandler):

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
            timeouts[client][work[0]] = tornado.ioloop.IOLoop.current().call_later(
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


class CancelWorkHandler(tornado.web.RequestHandler):

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
            tornado.ioloop.IOLoop.current().remove_timeout(
                timeouts[self.request.remote_ip][uri]
            )
            del timeouts[self.request.remote_ip][uri]
        except IndexError:
            # 401 - Not Authorized. Client was not assigned this work
            self.set_status(401)


class StatusHandler(tornado.web.RequestHandler):
    r"""
    Reviewing progress of the current run or connected clients
    """

    def get(self):
        pass


class SetupHandler(tornado.web.RequestHandler):
    r"""
    Endpoint for fetching client-side configuration parameters
    """

    def initialize(self, config):
        self.config = config

    def get(self):
        self.write(json_encode(self.config))

    def post(self):
        registered.add(self.request.remote_ip)


class WorkWSHandler(tornado.websocket.WebSocketHandler):
    wschecks = dict()
    # def check_origin(self, origin):
    #     return True

    def open(self, *args):
        client = self.request.remote_ip
        if startwork:
            self.send_work()
            # while len(assignedwork[client]) < 15:
            #     # should we attempt to .pop() anyways and catch the exception?
            #     if len(stalework) > 0:
            #         work = stalework.pop()
            #     else:
            #         work = next(workgenerator)
            #     self.write_message(json_encode(
            #         {
            #             'batch': work[0],
            #             'players': work[1],
            #             'realm': work[2]
            #         }
            #     ))
            #     assignedwork[client][work[0]] = work
            #     timeouts[client][work[0]] = tornado.ioloop.IOLoop.current().call_later(
            #         server_config['timeout'],
            #         move_to_stale,
            #         client,
            #         work
            #     )
            # Check if the client has enough work every 200 ms
            WorkWSHandler.wschecks[client] = tornado.ioloop.PeriodicCallback(self.send_work, 200)
            WorkWSHandler.wschecks[client].start()


    def send_work(self):
        client = self.request.remote_ip
        while len(assignedwork[client]) < server_config['max tasks']:
            try:
                work = stalework.pop()
            except IndexError:
                work = next(workgenerator)
            self.write_message(json_encode(
                {
                    'batch': work[0],
                    'players': work[1],
                    'realm': work[2]
                }
            ))
            assignedwork[client][work[0]] = work
            timeouts[client][work[0]] = tornado.ioloop.IOLoop.current().call_later(
                server_config['timeout'],
                move_to_stale,
                client,
                work
            )

    # In the case of a client going offline, we can mark their work as "stale" here.
    # However, we already have timers set to do that and will let them handle it.
    def on_close(self):
        client = self.request.remote_ip
        WorkWSHandler.wschecks[client].stop()
        del WorkWSHandler.wschecks[client]

    def on_message(self, message):
        # Handle results feed, send new work
        if '{' in message:
            client = self.request.remote_ip
            work = json_decode(message)
            try:
                # Remove timeout first
                tornado.ioloop.IOLoop.current().remove_timeout(
                    timeouts[client][work['batch']]
                )
                del timeouts[client][work['batch']]
                del assignedwork[client][work['batch']]
                # global batches_complete
                # batches_complete += 1
            except KeyError:
                pass
            self.send_work()
            ## Calling a class method instead, to consolidate code
            # if len(assignedwork[client]) < server_config['max tasks']:
            #     # should we attempt to .pop() anyways and catch the exception?
            #     if len(stalework) > 0:
            #         work = stalework.pop()
            #     else:
            #         work = next(workgenerator)
            #     self.write_message(json_encode(
            #         {
            #             'batch': work[0],
            #             'players': work[1],
            #             'realm': work[2]
            #         }
            #     ))
            #     assignedwork[client][work[0]] = work
            #     timeouts[client][work[0]] = tornado.ioloop.IOLoop.current().call_later(
            #         server_config['timeout'],
            #         move_to_stale,
            #         client,
            #         work
            #     )
        ## We'll allow the work to time out instead of having clients cancel
        # elif 'cancel' in message:
        #     for batch in message.split()[1:]:
        #         batch = int(message.split()[-1])
        #         if batch not in assignedwork[self.request.remote_ip]:
        #             raise IndexError
        #         stalework.append(assignedwork[self.request.remote_ip][batch])
        #         del assignedwork[self.request.remote_ip][batch]
        #         tornado.ioloop.IOLoop.current().remove_timeout(
        #             timeouts[self.request.remote_ip][batch]
        #         )
        #         del timeouts[self.request.remote_ip][batch]

def make_app(sfiles, clientconfig):
    return tornado.web.Application([
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
        (r"/files/nix/([^/]*)",
         tornado.web.StaticFileHandler,
         {'path': pjoin(sfiles, 'nix')}),
        (r"/files/win/([^/]*)",
         tornado.web.StaticFileHandler,
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
    # TODO: Create a timer to change startwork
    startwork = True

    try:
        app = make_app(static_files, client_config)
        app.listen(args.port)
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        print('Shutting down')
        tornado.ioloop.IOLoop.current().stop()
