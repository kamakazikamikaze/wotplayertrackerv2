import aiohttp
import asyncio
from datetime import datetime
from functools import partial
import logging
from multiprocessing import Manager, Process
from os import mkdir
from os.path import exists
from pickle import dumps, loads
from queue import Empty
from urllib.parse import urljoin
import uvloop

from utils import load_config, APIResult, Player


class TrackerClientNode(object):
    # The API limits the number of requests per IP. Unless we develop a
    # solution for clients with multiple public IP addresses, which is
    # unlikely, we'll bind this to the class to share the work queue

    def __init__(self, config, session, work_queue):
        self.server = config['server']
        self.ssl = config['use ssl']
        self.endpoint = 'work'
        self.debug = False if 'debug' not in config else config['debug']
        self.session = session
        self._setupLogging()
        self.work_queue = work_queue

    def _setupLogging(self):
        if not exists('log'):
            mkdir('log')
        self.log = logging.getLogger('Client.Work')
        formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d | %(name)-14s | %(levelname)-8s | %(message)s',
            datefmt='%m-%d %H:%M:%S'
        )
        if self.debug:
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

    async def run(self):
        global workdone
        wsproto = 'ws' if not self.ssl else 'wss'
        async with self.session.ws_connect(
            urljoin(
                self.server.replace('http', wsproto),
                self.endpoint)
        ) as ws:
            self.ws = ws
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    for work in loads(msg.data):
                        self.work_queue.put_nowait(work)
                        self.log.debug('New task')
                elif msg.type == aiohttp.WSMsgType.CLOSE:
                    self.log.info('Server is closing connection')
                    workdone[-1] = True
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.log.error('Websocket error!')
                    break
            del self.ws


class TelemetryClientNode(object):

    def __init__(self, config, session):
        self.server = config['server']
        self.ssl = config['use ssl']
        self.endpoint = 'telemetry'
        self.session = session

    async def run(self):
        global workdone
        wsproto = 'ws' if not self.ssl else 'wss'
        async with self.session.ws_connect(
            urljoin(
                self.server.replace('http', wsproto),
                self.endpoint)
        ) as ws:
            while not workdone[-1]:
                await ws.send_str(
                    ',{},{},{},{},{},{},{},{}'.format(
                        # completed,
                        # timeouts,
                        # errors,
                        # emptyqueue
                        *workdone[0:5],
                        work_queue.qsize(),
                        result_queue.qsize(),
                        return_queue.qsize()
                    )
                )
                await asyncio.sleep(5)


class QueryAPI(object):

    data_fields = (
        'created_at,'
        'account_id,'
        'last_battle_time,'
        'nickname,'
        'updated_at,'
        'statistics.all.battles'
    )
    api_url = 'https://api-{}-console.worldoftanks.com/wotx/account/info/'

    def __init__(self, config, session, workqueue, resultqueue, workdone):
        self.key = config['application_id']
        self.debug = False if 'debug' not in config else config['debug']
        self.timeout = 5 if 'timeout' not in config else config['timeout']
        self._setupLogging()
        self.session = session
        self.work = workqueue
        self.results = resultqueue
        self.workdone = workdone

    def _setupLogging(self):
        if not exists('log'):
            mkdir('log')
        self.log = logging.getLogger('Client.Query')
        formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d | %(name)-14s | %(levelname)-8s | %(message)s',
            datefmt='%m-%d %H:%M:%S'
        )
        if self.debug:
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

    async def query(self):
        try:
            work = self.work.get_nowait()
        except Empty:
            self.log.warning('Queue empty')
            self.workdone[3] += 1
            return
        self.log.debug('Batch %i: Starting', work[0])
        start = datetime.now()
        params = {
            'account_id': ','.join(map(str, range(*work[1]))),
            'application_id': self.key,
            'fields': self.data_fields,
            'language': 'en'
        }
        try:
            self.workdone[4] += 1
            self.log.debug('Batch %i: Querying API', work[0])
            response = await self.session.get(
                self.api_url.format(work[2]),
                params=params
            )
            self.log.debug(
                'Batch %i: %f seconds to complete request',
                work[0],
                (datetime.now() - start).total_seconds()
            )
            self.workdone[4] -= 1
        except aiohttp.ClientConnectionError:
            self.workdone[4] -= 1
            self.workdone[1] += 1
            self.work.put_nowait(work)
            self.log.warning('Batch %i: Timeout reached', work[0])
            return
        if response.status != 200:
            self.work.put_nowait(work)
            self.log.warning(
                'Batch %i: Status code %i',
                work[0],
                response.status
            )
            self.workdone[2] += 1
            return
        result = await response.json()
        if 'error' in result:
            self.work.put_nowait(work)
            self.log.error('Batch %i: %s', work[0], str(result))
            return
        self.results.put_nowait(
            (
                result,
                start,
                work
            )
        )
        self.workdone[0] += 1
        end = datetime.now()
        self.log.debug(
            'Batch %i: %f seconds of runtime',
            work[0],
            (end - start).total_seconds()
        )


class ResultProcessor(object):

    def __init__(self, config, resultqueue, returnqueue, workdone):
        self.debug = False if 'debug' not in config else config['debug']
        self.results = resultqueue
        self.return_queue = returnqueue
        self.workdone = workdone
        self._setupLogging()

    def _setupLogging(self):
        if not exists('log'):
            mkdir('log')
        self.log = logging.getLogger('Client.Process')
        formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d | %(name)-14s | %(levelname)-8s | %(message)s',
            datefmt='%m-%d %H:%M:%S'
        )
        if self.debug:
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

    def run(self):
        while not self.workdone[-1]:
            try:
                response, start, work = self.results.get_nowait()
            except Empty:
                continue
            try:
                self.return_queue.put_nowait(
                    APIResult(
                        tuple(
                            Player(
                                p['account_id'],
                                p['nickname'],
                                p['created_at'],
                                p['last_battle_time'],
                                p['updated_at'],
                                p['statistics']['all']['battles']
                            ) for __, p in response['data'].items() if p),
                        start.timestamp(),
                        work[2],
                        work[0]
                    )
                )
            except KeyError:
                self.log.warning('Batch %i has no "data" key', work[0])
                self.log.warning('Batch %i: %s', work[0], str(response))


async def work_handler(config, workqueue, returnqueue, workdone):
    loop = asyncio.get_running_loop()
    # Share a session between both websocket handlers
    async with aiohttp.ClientSession() as session:
        client = TrackerClientNode(config, session, workqueue)
        if 'telemetry' in config:
            telemetry = TelemetryClientNode(config, session)
            asyncio.ensure_future(telemetry.run())
        asyncio.ensure_future(client.run())
        while not workdone[-1]:
            if hasattr(client, 'ws'):
                try:
                    result = await loop.run_in_executor(None, returnqueue.get_nowait)
                except Empty:
                    continue
                await client.ws.send_bytes(dumps(result))
            else:
                await asyncio.sleep(0.005)


async def query_loop(config, workqueue, resultqueue, workdone, workers):
    gap = (1 / config['throttle']) * workers
    async with aiohttp.ClientSession() as session:
        worker = QueryAPI(config, session, workqueue, resultqueue, workdone)
        # Reference: https://stackoverflow.com/a/48682456/1993468
        while not workdone[-1]:
            asyncio.ensure_future(worker.query())
            await asyncio.sleep(gap)


def query_hander(config, workqueue, resultqueue, workdone, workers):
    # uvloop.install()
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.run(
        # loop.run_until_complete(
        query_loop(
            config,
            workqueue,
            resultqueue,
            workdone,
            workers
        )
    )


if __name__ == '__main__':
    from argparse import ArgumentParser
    agp = ArgumentParser()
    agp.add_argument(
        'config',
        help='Client configuration file to use',
        default='./config/client.json')
    args = agp.parse_args()
    manager = Manager()
    workdone = manager.list()
    workdone.append(0)  # completed
    workdone.append(0)  # timeouts
    workdone.append(0)  # errors
    workdone.append(0)  # emptyqueue
    workdone.append(0)  # active queries
    workdone.append(False)  # Work is done
    work_queue = manager.Queue()
    result_queue = manager.Queue()
    return_queue = manager.Queue()
    workers = 2
    try:
        # uvloop.install()
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        loop = asyncio.get_event_loop()
        config = load_config(args.config)
        query_workers = [Process(
            target=query_hander,
            args=(
                config,
                work_queue,
                result_queue,
                workdone,
                workers
            )
        ) for _ in range(workers)]
        result_processor = ResultProcessor(
            config, result_queue, return_queue, workdone)
        result_worker = Process(target=result_processor.run)
        for worker in query_workers:
            worker.start()
        result_worker.start()
        asyncio.run(
            # loop.run_until_complete(
            work_handler(
                config,
                work_queue,
                return_queue,
                workdone
            )
        )
        for worker in query_workers:
            worker.join()
        result_worker.join()
    except KeyboardInterrupt:
        print('Shutting down')
        ioloop.IOLoop.current().stop()
        exitcall.stop()
        for worker in query_workers:
            worker.terminate()
        result_processor.terminate()
