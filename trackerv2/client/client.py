from tornado import ioloop
from tornado.escape import json_decode, json_encode
from tornado.httpclient import AsyncHTTPClient  # , HTTPRequest
from tornado.httputil import url_concat
from tornado.queues import Queue, QueueEmpty
from tornado.websocket import websocket_connect
from urllib.parse import urljoin
from utils import load_config  # , write_config
# from wotconsole import player_data, WOTXResponseError

workdone = False


class TrackerClientNode:
    # The API limits the number of requests per IP. Unless we develop a
    # solution for clients with multiple public IP addresses, which is
    # unlikely, we'll bind this to the class to share the work queue
    workqueue = Queue()
    data_fields = (
        'created_at',
        'account_id',
        'last_battle_time',
        'nickname',
        'updated_at',
        'statistics.all.battles'
    )
    api_url = 'https://api-{}-console.worldoftanks.com/wotx/'

    def __init__(self, config):
        self.server = config['server']
        self.throttle = 10 if 'throttle' not in config else config['throttle']
        self.key = config['application_id']
        self.debug = False if 'debug' not in config else config['debug']
        self.timeout = 5 if 'timeout' not in config else config['timeout']
        self.schedule = ioloop.PeriodicCallback(
            self.query, 1000 // self.throttle)
        self.http_client = AsyncHTTPClient()

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
        params = {
            'account_id': ','.join(map(str, work['players'])),
            'application_id': self.key,
            'fields': ','.join(map(str, TrackerClientNode.data_fields)),
            'language': 'en'
        }
        # TODO: Handle API errors
        url = url_concat(
            TrackerClientNode.api_url.format(work['realm']) + 'account/info/',
            params)
        # req = HTTPRequest(url, 'GET')
        response = await self.http_client.fetch(
            url,
            request_timeout=self.timeout)
        # await self.send_results(work)
        # result = {'batch': work['batch']}
        result = json_decode(response.body)['data']  # IndexError if missing
        # time.time() which is epoch (UTC). No need to create a timestamp here
        result['_last_api_pull'] = response.request.start_time
        result['batch'] = work['batch']
        result['console'] = work['realm']
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

    # def __del__(self):
    #     self.schedule.stop()


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
    try:
        config = load_config(args.config)
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
