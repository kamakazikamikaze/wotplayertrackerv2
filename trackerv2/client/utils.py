from hashlib import sha1
from json import load, dump
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
    console: str
    spotted: int
    wins: int
    damage_dealt: int
    frags: int
    dropped_capture_points: int


class APIResult(NamedTuple):
    players: tuple
    last_api_pull: int
    batch: int
