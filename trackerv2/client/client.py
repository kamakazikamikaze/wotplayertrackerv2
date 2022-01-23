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

    def __init__(self, config, session, work_queue, workdone):
        self.server = config['server']
        self.ssl = config['use ssl']
        self.endpoint = 'work'
        self.debug = False if 'debug' not in config else config['debug']
        self.session = session
        self._setupLogging()
        self.work_queue = work_queue
        self.workdone = workdone

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
        wsproto = 'ws' if not self.ssl else 'wss'
        async with self.session.ws_connect(
            urljoin(
                self.server.replace('http', wsproto),
                self.endpoint
            )
        ) as ws:
            self.ws = ws
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    for work in loads(msg.data):
                        self.work_queue.put_nowait(work)
                        self.log.debug('New task')
                elif msg.type in (aiohttp.WSMsgType.CLOSE.
                                  aiohttp.WSMsgType.CLOSING,
                                  aiohttp.WSMsgType.CLOSED):
                    self.log.info('Server is closing connection')
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.log.error('Websocket error!')
                    break
                else:
                    self.log.error('Unknown type: %s', str(msg.type))
            self.workdone[-1] = True
            del self.ws


class TelemetryClientNode(object):

    def __init__(self, config, session, workdone):
        self.server = config['server']
        self.ssl = config['use ssl']
        self.endpoint = 'telemetry'
        self.session = session
        self.sleep = config['telemetry']
        self.workdone = workdone

    async def run(self):
        global workdone
        wsproto = 'ws' if not self.ssl else 'wss'
        async with self.session.ws_connect(
            urljoin(
                self.server.replace('http', wsproto),
                self.endpoint
            )
        ) as ws:
            while not self.workdone[-1]:
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
                await asyncio.sleep(self.sleep)


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
                # Ok to block
                response, start, work = self.results.get(timeout=1)
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
                                    p['statistics']['all']['battles'],
                                    'xbox' if p['nickname'][-2:] == '-x' else 'ps',
                                    p['statistics']['all']['wins'],
                                    p['statistics']['all']['damage_dealt'],
                                    p['statistics']['all']['frags'],
                                    p['statistics']['all']['dropped_capture_points']
                                ) for __, p in response['data'].items() if p),
                            start.timestamp(),
                            work[0]
                        )
                    )
                except KeyError:
                    self.log.warning('Batch %i has no "data" key', work[0])
                    self.log.warning('Batch %i: %s', work[0], str(response))
            except Empty:
                pass


def _setupLogging(config):
    debug = False if 'debug' not in config else config['debug']
    if not exists('log'):
        mkdir('log')
    log = logging.getLogger('Client.Query')
    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d | %(name)-14s | %(levelname)-8s | %(message)s',
        datefmt='%m-%d %H:%M:%S'
    )
    if debug:
        ch = logging.StreamHandler()
        ch.setLevel(logging.WARNING)
        ch.setFormatter(formatter)
        fh = logging.FileHandler(
            datetime.now().strftime('log/client_%Y_%m_%d.log'))
        fh.setLevel(logging.DEBUG)
        ch.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        log.addHandler(fh)
        log.addHandler(ch)
    else:
        nu = logging.NullHandler()
        log.addHandler(nu)
    log.setLevel(logging.DEBUG if debug else logging.INFO)
    return log


async def query(key, session, workqueue, resultqueue, workdone, log):
    try:
        work = workqueue.get_nowait()
    except Empty:
        log.warning('Queue empty')
        workdone[3] += 1
        return
    api_url = 'https://api-console.worldoftanks.com/wotx/account/info/'
    log.debug('Batch %i: Starting', work[0])
    start = datetime.now()
    params = {
        'account_id': ','.join(map(str, range(*work[1]))),
        'application_id': key,
        'fields': (
            'created_at,'
            'account_id,'
            'last_battle_time,'
            'nickname,'
            'updated_at,'
            'statistics.all.battles,'
            'statistics.all.wins,'
            'statistics.all.damage_dealt,'
            'statistics.all.frags,'
            'statistics.all.dropped_capture_points'
        ),
        'language': 'en'
    }
    try:
        log.debug('Batch %i: Querying API', work[0])
        response = await session.get(
            api_url,
            params=params
        )
        log.debug(
            'Batch %i: %f seconds to complete request',
            work[0],
            (datetime.now() - start).total_seconds()
        )
    except aiohttp.ClientConnectionError:
        workdone[1] += 1
        workqueue.put_nowait(work)
        log.warning('Batch %i: Timeout reached', work[0])
        return
    if response.status != 200:
        workqueue.put_nowait(work)
        log.warning(
            'Batch %i: Status code %i',
            work[0],
            response.status
        )
        workdone[2] += 1
        return
    log.debug('Batch %i: Awaiting full result response', work[0])
    result = await response.json()
    if 'error' in result:
        workqueue.put_nowait(work)
        log.error('Batch %i: %s', work[0], str(result))
        return
    log.debug('Batch %i: Sending JSON to result queue', work[0])
    resultqueue.put_nowait(
        (
            result,
            start,
            work
        )
    )
    workdone[0] += 1
    end = datetime.now()
    log.debug(
        'Batch %i: %f seconds of runtime',
        work[0],
        (end - start).total_seconds()
    )


async def work_handler(config, workqueue, returnqueue, workdone):
    loop = asyncio.get_running_loop()
    # Share a session between both websocket handlers
    async with aiohttp.ClientSession() as session:
        client = TrackerClientNode(config, session, workqueue, workdone)
        if 'telemetry' in config:
            telemetry = TelemetryClientNode(config, session, workdone)
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
                await asyncio.sleep(0.05)


async def query_loop(config, workqueue, resultqueue, workdone, workers):
    gap = (1 / config['throttle']) * workers
    conn = aiohttp.TCPConnector(ttl_dns_cache=3600)
    async with aiohttp.ClientSession(connector=conn) as session:
        log = _setupLogging(config)
        # Reference: https://stackoverflow.com/a/48682456/1993468
        while not workdone[-1]:
            asyncio.ensure_future(
                query(
                    config['application_id'],
                    session,
                    workqueue,
                    resultqueue,
                    workdone,
                    log
                )
            )
            workdone[4] = len(asyncio.all_tasks())
            await asyncio.sleep(gap)


def query_hander(config, workqueue, resultqueue, workdone, workers):
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.run(
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
    workers = 1
    try:
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        loop = asyncio.get_event_loop()
        config = load_config(args.config)
        query_workers = [
            Process(
                target=query_hander,
                args=(
                    config,
                    work_queue,
                    result_queue,
                    workdone,
                    workers
                )
            ) for _ in range(workers)
        ]
        result_processor = ResultProcessor(
            config, result_queue, return_queue, workdone)
        result_worker = Process(target=result_processor.run)
        for worker in query_workers:
            worker.start()
        result_worker.start()
        asyncio.run(
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
        for worker in query_workers:
            worker.terminate()
        result_worker.terminate()
