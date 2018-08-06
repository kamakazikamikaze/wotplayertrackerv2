from platform import system
from tornado import ioloop
from tornado.escape import json_decode, json_encode
from tornado.httpclient import AsyncHTTPClient, HTTPClient, HTTPRequest
from tornado.queues import Queue, QueueEmpty
from tornado.websocket import websocket_connect
from urllib.parse import urljoin
from utils import load_config, write_config
# TODO: Add async capability to wotconsole, limiting to Python 3.5+, using
# aiohttp
# from wotconsole import player_data, WOTXResponseError

workdone = False


class TrackerClientNode:
    # The API limits the number of requests per IP. Unless we develop a
    # solution for clients with multiple public IP addresses, which is
    # unlikely, we'll bind this to the class to share the work queue
    workqueue = Queue()

    def __init__(self, config):
        self.server = config['server']
        self.throttle = config['throttle']
        self.key = config['application_id']
        self.debug = config['debug']
        self.schedule = ioloop.PeriodicCallback(
            self.query, 1000 // self.throttle)

    def on_message(self, message):
        if message is not None:
            TrackerClientNode.workqueue.put_nowait(json_decode(message))
        else:
            global workdone
            self.stop()
            self.conn.close()
            workdone = True

    async def query(self):
        try:
            # Don't use .get() here, as the client may connect minutes early.
            # We don't want a huge backlog of query calls...
            work = TrackerClientNode.workqueue.get_nowait()
        except QueueEmpty:
            return
        # Debugging for now. Print out incoming work
        print('Prcoessed batch:', work['batch'])
        # await self.send_results(work)
        result = {'batch': work['batch']}
        await self.conn.write_message(json_encode(result))

    # async def send_results(self, result):
    #     # Don't block messages to server
    #     await self.conn.write_message(json_encode(result))

    async def connect(self):
        self.conn = await websocket_connect(
            urljoin(self.server.replace('http', 'ws'), 'wswork'),
            on_message_callback=self.on_message
        )

    def start(self):
        # Query the API no more than $throttle times per second
        self.schedule.start()
        # This may have undesirable effects if imported into a different
        # project scope. We'll have implicit IOLoop calls outside the class
        # for safety.
        # ioloop.IOLoop.current().start()

    def stop(self):
        self.schedule.stop()

    def __del__(self):
        self.schedule.stop()


def download_file():
    pass


def setup(config, configfile):
    http_client = HTTPClient()
    async_http_client = AsyncHTTPClient()
    newconfig = json_decode(
        http_client.fetch(
            urljoin(
                config['server'],
                'setup')))
    if system() == 'Windows':
        plat = 'win'
    else:
        plat = 'nix'
    for filename in newwconfig['files']:
        # Get hash
        # Send hash in request
        pass
    del newconfig['files']
    write_config(configfile, newconfig)
    config = newconfig
    http_client.fetch(
        HTTPRequest(
            urljoin(
                config['server'],
                'setup'),
            'POST',
            allow_nonstandard_methods=True))
    return config


def try_exit():
    if workdone:
        print('Work complete. Shutting down client')
        ioloop.IOLoop.current().stop()

if __name__ == '__main__':
    from argparse import ArgumentParser
    agp = ArgumentParser()
    # TODO: Handle REST loop
    # agp.add_argument(
    #     '-r',
    #     '--restful',
    #     help='Use REST API instead of websockets',
    #     default=False,
    #     action='store_true')
    agp.add_argument(
        'config',
        help='Client configuration file to use',
        default='./config/client.json')
    args = agp.parse_args()
    config = load_config(args.config)

    try:
        config = setup(config, args.config)
        client = TrackerClientNode(config)
        # client.connect()
        ioloop.IOLoop.current().run_sync(client.connect)
        client.start()
        exitcall = ioloop.PeriodicCallback(try_exit, 1000)
        exitcall.start()
        ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        print('Shutting down')
        ioloop.IOLoop.current().stop()
        exitcall.stop()
