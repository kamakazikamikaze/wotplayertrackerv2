from collections import defaultdict
from hashlib import sha1
from json import load, dump
from os import walk
from os.path import join as pjoin
from uuid import NAMESPACE_DNS, uuid5

BUF_SIZE = 65536


def getsha1(filename):
    sha1hash = sha1()
    with open(filename, 'rb') as f:
        while True:
            data = f.read(BUF_SIZE)
            if not data:
                break
            sha1hash.update(data)
    return sha1hash.hexdigest()


def genuuid(ip):
    return str(uuid5(NAMESPACE_DNS, ip))


def genhashes(dirpath='./files'):
    hashes = {}
    for _, dirs, _ in walk(dirpath):
        for d in dirs:
            hashes[d] = {}
            for _, _, files in walk(pjoin(dirpath, d)):
                for fi in files:
                    hashes[d][fi] = getsha1(pjoin(dirpath, d, fi))
    return hashes


def load_config(filename='./config/server.json'):
    with open(filename) as f:
        return load(f)


def write_config(config, filename='./config/server.json'):
    with open(filename, 'w') as f:
        dump(config, f, indent=4)


def create_client_config(filename='./config/client.json'):
    config = {
        'application_id': 'demo',
        'throttle': 10,
        'server': 'http://replaceme/',
        'ws endpoint': 'wswork',
        'use ssl': False,
        'timeout': 5}
    write_config(config, filename)


def create_server_config(filename='./config/server.json'):
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
            'start account': 5000,
            'max account': 14000000
        },
        'ps4': {
            'start account': 1073740000,
            'max account': 1082000000
        },
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
        }
    }
    with open(filename, 'w') as f:
        dump(newconfig, f, indent=4)


def nested_dd():
    return defaultdict(nested_dd)
