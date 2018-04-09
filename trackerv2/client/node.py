from datetime import datetime
from multiprocessing import Manager, Process, Pool
from sys import version_info
from wotconsole import player_data, WOTXResponseError
from .utils import RatedSemaphore


if version_info.major == 2:
    def query(api_token, workinfo, error_q, result_q):
        r"""
        Pull information from Wargaming's API
        """
        data_fields = (
            'created_at',
            'account_id',
            'last_battle_time',
            'nickname',
            'updated_at',
            'statistics.all.battles'
        )
        with rate_limit:
            try:
                pulltime = datetime.utcnow()
                response = player_data(
                    workinfo['players'],
                    api_token,
                    fields=data_fields,
                    api_realm=workinfo['realm'],
                    timeout=workinfo['timeout']
                )
                response['_last_api_pull'] = pulltime
                result_q.push(response)
            except WOTXResponseError as wote:
                error_q.put(wote)
else:
    def query(api_token, workinfo, error_q):
        r"""
        Pull information from Wargaming's API
        """
        data_fields = (
            'created_at',
            'account_id',
            'last_battle_time',
            'nickname',
            'updated_at',
            'statistics.all.battles'
        )
        with rate_limit:
            try:
                pulltime = datetime.utcnow()
                response = player_data(
                    workinfo['players'],
                    api_token,
                    fields=data_fields,
                    api_realm=workinfo['realm'],
                    timeout=workinfo['timeout']
                )
                response['_last_api_pull'] = pulltime
                return response
            except WOTXResponseError as wote:
                error_q.put(wote)

    results = Manager().Queue()

    def push_result(result):
        if result is not None:
            results.push(result)


def init_worker(lock_):
    global rate_limit
    rate_limit = lock_


def collect(config, work_q):
    rate_limit = RatedSemaphore(10)
    # work = Manager().Queue()
    errors = Manager().Queue()
    if version_info == 2:
        results = Manager().Queue()
    with Pool(
            config['pool size'],
            initializer=init_worker,
            initargs=(rate_limit,),
            maxtasksperchild=50) as pool:
        while True:
            w = work_q.get()
            if w is not None:
                if version_info.major == 2:
                    pool.apply_async(
                        query,
                        args=(
                            config['api token'],
                            w,
                            errors,
                            results,
                        ),
                    )
                else:
                    pool.apply_async(
                        query,
                        args=(
                            config['api token'],
                            w,
                            errors,
                        ),
                        callback=push_result
                    )
            else:
                pool.close()
                pool.join()


def start(config):
    pass
