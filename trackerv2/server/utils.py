from collections import defaultdict
from hashlib import sha1
from ipaddress import ip_network
from json import load, dump
from os import walk
from os.path import join as pjoin
from uuid import NAMESPACE_DNS, uuid5
from typing import NamedTuple

from constants import XBOX_MIN, XBOX_MAX, PS4_MIN, PS4_MAX

BUF_SIZE = 65536


def getsha1(filename : str) -> str:
    sha1hash = sha1()
    with open(filename, 'rb') as f:
        while True:
            data = f.read(BUF_SIZE)
            if not data:
                break
            sha1hash.update(data)
    return sha1hash.hexdigest()


def genuuid(ip : str) -> str:
    return str(uuid5(NAMESPACE_DNS, ip))


def genhashes(dirpath : str = './files') -> dict:
    hashes = {}
    for _, dirs, _ in walk(dirpath):
        for d in dirs:
            hashes[d] = {}
            for __, __, files in walk(pjoin(dirpath, d)):
                for fi in files:
                    hashes[d][fi] = getsha1(pjoin(dirpath, d, fi))
    return hashes


def load_config(filename : str='./config/server.json') -> dict:
    with open(filename) as f:
        return load(f)


def write_config(config : dict, filename : str = './config/server.json'):
    with open(filename, 'w') as f:
        dump(config, f, indent=4)


def create_client_config(filename : str = './config/client.json'):
    config = {
        'application_id': 'demo',
        'throttle': 10,
        'server': 'http://replaceme/',
        'use ssl': False,
        'timeout': 5,
        'debug': False,
        'telemetry': 5000  # milliseconds
    }
    write_config(config, filename)


def create_server_config(filename : str = './config/server.json'):
    newconfig = {
        'application_id': {
            'catchall': {
                'key': 'demo',
                'throttle': 10
            },
            'exampleapikey1': {
                'key': 'demo',
                'addresses': ['x.x.x.x'],
                'throttle': 20
            }
        },
        'language': 'en',
        'xbox': {
            'start account': XBOX_MIN,
            'max account': XBOX_MAX
        },
        'ps4': {
            'start account': PS4_MIN,
            'max account': PS4_MAX
        },
        'expand': True,
        'max retries': 5,
        'timeout': 15,
        'debug': False,
        'extra tasks': 10,
        'use whitelist': False,
        'whitelist': [],
        'blacklist': [],
        'port': 8888,
        'logging': {
            'level': 'warning',
            'file': 'logs/server-%Y_%m_%d'
        },
        'database': {
            'user': 'root',
            'password': 'password',
            'host': 'localhost',
            'port': 5432,
            'database': 'battletracker'
        },
        'elasticsearch': {
            'clusters': {
                '<cluster1>': {
                    'hosts': [],
                    'sniff_on_start': True,
                    'sniff_on_connection_fail': True,
                    'sniffer_timeout': 30
                }
            },
            'offload': {
                'data folder': '/srv/battletrackerv2/offload/dumps',
                'delete old index on reload': True,
                'index': '/srv/battletrackerv2/offload/index.txt'
            }
        },
        'debug access': ['127.0.0.1'],
        'telemetry': {
            'file': 'logs/telemetry-%Y_%m_%d',
            'interval': 5000  # milliseconds
        }
    }
    with open(filename, 'w') as f:
        dump(newconfig, f, indent=4)


def nested_dd():
    return defaultdict(nested_dd)


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

def expand_debug_access_ips(config : dict) -> list:
    if 'debug access' not in config:
        return [ip_network('127.0.0.1')]
    converted = []
    for network in config['debug access']:
        try:
            # This will work for any valid IP address
            address = ip_network(network)
        except ValueError:
            # Just skip any errors
            continue
        converted.append(address)
    return converted
