from argparse import ArgumentParser
from datetime import datetime
from functools import partial
import logging
from multiprocessing import Process, Manager, cpu_count
from os import mkdir
from os.path import exists
from pickle import dumps, loads
from queue import Empty
from tornado import ioloop
from tornado.escape import json_decode
from tornado.httpclient import AsyncHTTPClient
from tornado.httputil import url_concat
from tornado.queues import Queue, QueueEmpty
from tornado.simple_httpclient import HTTPTimeoutError
from tornado.websocket import websocket_connect
from urllib.parse import urljoin

from utils import load_config, APIResult, Player

timeouts = 0


def result_handler(queue, return_queue, work_done, identity):
    logger = logging.getLogger('Client')
    while True:
        if not queue.qsize():
            if len(work_done) >= 3:
                break
        try:
            work, response = queue.get_nowait()
        except Empty:
            continue
        try:
            players = APIResult(
                tuple(
                    Player(
                        p['account_id'],
                        p['nickname'],
                        p['created_at'],
                        p['last_battle_time'],
                        p['updated_at'],
                        p['statistics']['all']['battles']
                    ) for __, p in json_decode(
                        response.body)['data'].items() if p),
                response.request.start_time,
                work[2],
                work[0]
            )
            return_queue.put_nowait(players)
            logger.debug('Batch %i: Converted to APIResult', work[0])
            # completed += 1
            work_done[0] += 1
        except ValueError:
            # errors += 1
            work_done[1] += 1
            logger.error(
                'Batch %i: No data for %s',
                work[0],
                json_decode(response.body)
            )
        except KeyError:
            # errors += 1
            work_done[1] += 1
            logger.error('Batch %i: %s', work[0], response.body)


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
        self.loop = ioloop.IOLoop.current()

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
            self.log.debug('Got empty message from server')
            self.stop()
            self.conn.close()
            workdone.append(True)

    async def query(self):
        try:
            work = TrackerClientNode.workqueue.get_nowait()
        except QueueEmpty:
            self.log.debug('Empty queue')
            return
        global timeouts
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
        result_queue.put_nowait((work, response))
        self.log.debug('Batch %i: Sent to converter', work[0])
        # self.loop.call_later(
        #     self.throttle / 1000,
        #     partial(
        #         self.send_message,
        #         work[0],
        #     )
        # )
        try:
            await self.conn.write_message(
                dumps(
                    await self.loop.run_in_executor(
                        None,
                        func=partial(
                            send_queue.get,
                            True,
                            2
                        )
                    )
                ),
                True
            )
            self.log.debug('Batch %i: Sent data back to server', work[0])
        except Exception as e:
            self.log.error('Batch %i: %s', work[0], e)

    async def send_message(self, batch):
        self.log.debug('send_message %i: Invoked', batch)
        try:
            await self.conn.write_message(
                dumps(await self.loop.run_in_executor(
                    None,
                    func=partial(
                        send_queue.get,
                        True,
                        0.5
                    )
                )
                ),
                True
            )
            self.log.debug('send_message %i: Message sent', batch)
        except Exception as e:
            self.log.error('send_message %i: %s', batch, e)

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
                # completed,
                workdone[0],
                timeouts,
                # errors
                workdone[1]
            )
        )

    def start(self):
        self.schedule.start()

    def stop(self):
        self.schedule.stop()


def try_exit():
    if len(workdone) >= 3:
        for converter in converters:
            converter.join()
        i = 0
        # allow t
        while send_queue.qsize() and i < 10000:
            i += 1

        print('Work complete. Shutting down client')
        ioloop.IOLoop.current().stop()

if __name__ == '__main__':
    agp = ArgumentParser()
    agp.add_argument(
        'config',
        help='Client configuration file to use',
        default='./config/client.json')
    args = agp.parse_args()
    manager = Manager()
    result_queue = manager.Queue()
    send_queue = manager.Queue()
    workdone = manager.list()
    # completed -> [0]
    workdone.append(0)
    # errors -> [1]
    workdone.append(0)
    try:
        config = load_config(args.config)
        proc_count = config['processes'] if 'processes' in config and config[
            'processes'] >= 1 else 1
        client = TrackerClientNode(config)
        converters = [Process(
            target=result_handler,
            args=(
                result_queue,
                send_queue,
                workdone,
                i
            )
        ) for i in range(proc_count)]
        ioloop.IOLoop.current().run_sync(client.connect)
        client.start()
        if 'telemetry' in config:
            telemetry = TelemetryClientNode(config)
            ioloop.IOLoop.current().run_sync(telemetry.connect)
            telemetry.start()
        exitcall = ioloop.PeriodicCallback(try_exit, 1000)
        exitcall.start()
        for converter in converters:
            converter.start()
        ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        print('Shutting down')
        ioloop.IOLoop.current().stop()
        try:
            for converter in converters:
                converter.terminate()
            exitcall.stop()
        except NameError:
            pass
