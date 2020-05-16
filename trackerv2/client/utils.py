from hashlib import sha1
from json import load, dump
# from multiprocessing import BoundedSemaphore
from threading import Timer
# from threading import _BoundedSemaphore as BoundedSemaphore, Timer
from time import sleep
from tornado.locks import BoundedSemaphore
from typing import NamedTuple


def getsha1(filename, buffer_size=65536):
    sha1hash = sha1()
    with open(filename, 'rb') as f:
        while True:
            data = f.read(buffer_size)
            if not data:
                break
            sha1hash.update(data)
    return sha1hash.hexdigest()


# https://stackoverflow.com/a/16686329/1993468
class RatedSemaphore(BoundedSemaphore):
    """Limit to 1 request per `period / value` seconds (over long run)."""

    def __init__(self, value=1, period=1):
        BoundedSemaphore.__init__(self, value)
        t = Timer(period, self._add_token_loop,
                  kwargs=dict(time_delta=float(period) / value))
        t.daemon = True
        t.start()

    def _add_token_loop(self, time_delta):
        """Add token every time_delta seconds."""
        while True:
            try:
                BoundedSemaphore.release(self)
            except ValueError:  # ignore if already max possible value
                pass
            sleep(time_delta)  # ignore EINTR

    def release(self):
        pass  # do nothing (only time-based release() is allowed)


def load_config(filename='./config/client.json'):
    with open(filename) as f:
        return load(f)


def write_config(config, filename='./config/client.json'):
    with open(filename, 'w') as f:
        dump(config, f, indent=4)


class Player(NamedTuple):
    account_id: int
    nickname: str
    created_at: int
    last_battle_time: int
    updated_at: int
    battles: int


class APIResult(NamedTuple):
    players: bytes
    last_api_pull: int
    console: str
    batch: int
