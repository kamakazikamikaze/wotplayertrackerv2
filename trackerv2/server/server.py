from json.decoder import JSONDecodeError
import tornado.ioloop
import tornado.web
from tornado.escape import json_decode, json_encode
from utils import genuuid, genhashes
from os.path import join as pjoin


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
        pass


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

    def get(self):
        pass


def make_app(sfiles):
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/uuid", UUIDHandler),
        (r"/setup", SetupHandler),
        # (r"/updates/([^/]*)", UpdateHandler),
        (r"/updates", UpdateHandler),
        (r"/work", WorkHandler),
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
    args = agp.parse_args()
    static_files = args.static_files
    hashes = genhashes(static_files)
    try:
        app = make_app(static_files)
        app.listen(args.port)
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        print('Shutting down')
        tornado.ioloop.IOLoop.current().stop()
