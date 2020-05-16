from datetime import datetime
import logging
from os import mkdir
from os.path import exists
from pickle import dumps, loads
from tornado import ioloop
from tornado.escape import json_decode
from tornado.httpclient import AsyncHTTPClient
from tornado.httputil import url_concat
from tornado.queues import Queue, QueueEmpty
from tornado.simple_httpclient import HTTPTimeoutError
from tornado.websocket import websocket_connect
from urllib.parse import urljoin

from utils import load_config, APIResult  # , Player

workdone = False
completed = 0
timeouts = 0
errors = 0


class TrackerClientNode:
    # The API limits the number of requests per IP. Unless we develop a
    # solution for clients with multiple public IP addresses, which is
    # unlikely, we'll bind this to the class to share the work queue
    workqueue = Queue()
    data_fields = (
        'created_at,'
        'account_id,'
        'last_battle_time,'
        'nickname,'
        'updated_at,'
        'statistics.all.battles'
    )
    api_url = 'https://api-{}-console.worldoftanks.com/wotx/'

    def __init__(self, config):
        self.server = config['server']
        self.ssl = config['use ssl']
        # self.endpoint = config['ws endpoint']
        self.endpoint = 'work'
        self.throttle = 10 if 'throttle' not in config else config['throttle']
        self.key = config['application_id']
        self.debug = False if 'debug' not in config else config['debug']
        self.timeout = 5 if 'timeout' not in config else config['timeout']
        self.schedule = ioloop.PeriodicCallback(
            self.query,
            1000 // self.throttle
        )
        self.http_client = AsyncHTTPClient(max_clients=(self.throttle * 2))
        self._setupLogging()

    def _setupLogging(self):
        if not exists('log'):
            mkdir('log')
        self.log = logging.getLogger('Client')
        formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d | %(name)s | %(levelname)-8s | %(message)s',
            datefmt='%m-%d %H:%M:%S'
        )
        if self.debug:
            # self.log.propagate = True
            ch = logging.StreamHandler()
            ch.setLevel(logging.WARNING)
            ch.setFormatter(formatter)
            fh = logging.FileHandler(
                datetime.now().strftime('log/client_%Y_%m_%d.log'))
            fh.setLevel(logging.DEBUG)
            ch.setLevel(logging.DEBUG)
            fh.setFormatter(formatter)
            self.log.addHandler(fh)
            self.log.addHandler(ch)
        else:
            nu = logging.NullHandler()
            self.log.addHandler(nu)
        self.log.setLevel(logging.DEBUG if self.debug else logging.INFO)

    def on_message(self, message):
        if message is not None:
            TrackerClientNode.workqueue.put_nowait(loads(message))
            self.log.debug('Got work from server')
        else:
            global workdone
            self.stop()
            self.conn.close()
            workdone = True

    async def query(self):
        try:
            work = TrackerClientNode.workqueue.get_nowait()
        except QueueEmpty:
            self.log.debug('Empty queue')
            return
        global completed
        global timeouts
        global errors
        self.log.debug('Batch %i: Starting', work[0])
        start = datetime.now()
        params = {
            'account_id': ','.join(map(str, range(*work[1]))),
            'application_id': self.key,
            'fields': TrackerClientNode.data_fields,
            'language': 'en'
        }
        url = url_concat(
            TrackerClientNode.api_url.format(work[2]) + 'account/info/',
            params)
        try:
            self.log.debug('Batch %i: Querying API', work[0])
            response = await self.http_client.fetch(
                url,
                request_timeout=self.timeout)
            self.log.debug(
                'Batch %i: %f seconds to complete request',
                work[0],
                response.request_time)
        except HTTPTimeoutError:
            timeouts += 1
            TrackerClientNode.workqueue.put_nowait(work)
            self.log.warning('Batch %i: Timeout reached', work[0])
            return
        if response.code != 200:
            TrackerClientNode.workqueue.put_nowait(work)
            self.log.warning(
                'Batch %i: Status code %i',
                work[0],
                response.code
            )
            errors += 1
            return
        await self.conn.write_message(
            dumps(
                APIResult(
                    response.body,
                    response.request.start_time,
                    work[2],
                    work[0]
                )
            ),
            True
        )
        completed += 1
        end = datetime.now()
        self.log.debug(
            'Batch %i: %f seconds of runtime',
            work[0],
            (end - start).total_seconds()
        )
        # try:
        #     a = APIResult(
        #         tuple(
        #             Player(
        #                 p['account_id'],
        #                 p['nickname'],
        #                 p['created_at'],
        #                 p['last_battle_time'],
        #                 p['updated_at'],
        #                 p['statistics']['all']['battles']
        #             ) for __, p in json_decode(
        #                 response.body)['data'].items() if p),
        #         response.request.start_time,
        #         work[2],
        #         work[0]
        #     )
        #     completed += 1
        #     await self.conn.write_message(dumps(a), True)
        #     end = datetime.now()
        #     self.log.debug(
        #         'Batch %i: %f seconds of runtime',
        #         work[0],
        #         (end - start).total_seconds()
        #     )
        # except ValueError:
        #     errors += 1
        #     self.log.error(
        #         'Batch %i: No data for %s',
        #         work[0],
        #         json_decode(response.body)
        #     )
        # except KeyError:
        #     errors += 1
        #     self.log.error('Batch %i: %s', work[0], response.body)

    async def connect(self):
        wsproto = 'ws' if not self.ssl else 'wss'
        self.conn = await websocket_connect(
            urljoin(self.server.replace('http', wsproto), self.endpoint),
            on_message_callback=self.on_message
        )

    def start(self):
        self.schedule.start()

    def stop(self):
        self.schedule.stop()


class TelemetryClientNode:

    def __init__(self, config):
        self.server = config['server']
        self.ssl = config['use ssl']
        # self.endpoint = config['telemetry endpoint']
        self.endpoint = 'telemetry'
        self.schedule = ioloop.PeriodicCallback(
            self.send_update,
            config['telemetry']
        )

    async def connect(self):
        wsproto = 'ws' if not self.ssl else 'wss'
        self.conn = await websocket_connect(
            urljoin(self.server.replace('http', wsproto), self.endpoint),
            on_message_callback=self.on_message
        )

    def on_message(self, message):
        # Shouldn't expect anything. One-way.
        pass

    async def send_update(self):
        self.conn.write_message(
            ',{},{},{}'.format(
                completed,
                timeouts,
                errors
            )
        )

    def start(self):
        self.schedule.start()

    def stop(self):
        self.schedule.stop()


def try_exit():
    if workdone:
        print('Work complete. Shutting down client')
        ioloop.IOLoop.current().stop()

if __name__ == '__main__':
    from argparse import ArgumentParser
    agp = ArgumentParser()
    agp.add_argument(
        'config',
        help='Client configuration file to use',
        default='./config/client.json')
    args = agp.parse_args()
    try:
        config = load_config(args.config)
        client = TrackerClientNode(config)
        ioloop.IOLoop.current().run_sync(client.connect)
        client.start()
        if 'telemetry' in config:
            telemetry = TelemetryClientNode(config)
            ioloop.IOLoop.current().run_sync(telemetry.connect)
            telemetry.start()
        exitcall = ioloop.PeriodicCallback(try_exit, 1000)
        exitcall.start()
        ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        print('Shutting down')
        ioloop.IOLoop.current().stop()
        exitcall.stop()
