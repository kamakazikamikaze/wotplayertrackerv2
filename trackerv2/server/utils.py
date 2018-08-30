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


def create_client_config(filename='./config/client.json'):
    with open(filename, 'w') as f:
        dump({
            'application_id': 'replaceme',
            'throttle': 10,
            'server': 'http://replaceme/',
            'timeout': 5},
            f, indent=4)


def create_server_config(filename='./config/server.json'):
    newconfig = {
        'application_id': 'demo',
        'language': 'en',
        'xbox': {
            'start account': 5000,
            'max account': 13325000
        },
        'ps4': {
            'start account': 1073740000,
            'max account': 1080500000
        },
        'max retries': 5,
        'timeout': 15,
        'debug': False,
        'max tasks': 15,
        'logging': {
            'errors': 'logs/error-%Y_%m_%d'
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
