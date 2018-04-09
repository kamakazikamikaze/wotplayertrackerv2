from collections import deque
from itertools import chain
from json import load, dump
from uuid import NAMESPACE_DNS, uuid5
from os import walk
from os.path import join as pjoin
from hashlib import sha1

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


def load_config(filename='./config/server.json'):
    with open(filename) as f:
        return load(f)


def genhashes(dirpath='./files'):
    hashes = {}
    for _, dirs, _ in walk(dirpath):
        for d in dirs:
            hashes[d] = {}
            for _, _, files in walk(pjoin(dirpath, d)):
                for fi in files:
                    hashes[d][fi] = getsha1(pjoin(dirpath, d, fi))
    return hashes


def setup_work(config):
    r"""
    Create the initial player groups for workers to query

    Work is stored in the format of (tuple(player IDs), realm)

    :returns: Work tasks for nodes
    :rtype: deque
    """
    xbox_start_account = 5000 if 'start account' not in config[
        'xbox'] else config['xbox']['start account']
    xbox_max_account = 13325000 if 'max account' not in config[
        'xbox'] else config['xbox']['max account']
    ps4_start_account = 1073740000 if 'start account' not in config[
        'ps4'] else config['ps4']['start account']
    ps4_max_account = 1080500000 if 'max account' not in config[
        'ps4'] else config['ps4']['max account']

    playerschain = generate_players(
        xbox_start_account,
        xbox_max_account,
        ps4_start_account,
        ps4_max_account
    )
    work_queue = deque()

    realm = 'xbox'
    plist = []
    p = playerschain.next()
    while p <= xbox_max_account:
        if len(plist) == 100:
            work_queue.append((tuple(plist), realm))
            plist = []
        plist.append(p)
        p = playerschain.next()
    if plist:
        work_queue.append((tuple(plist), realm))
    plist = []
    realm = 'ps4'
    try:
        # Replace with `while True`?
        while p <= ps4_max_account:
            if len(plist) == 100:
                work_queue.append((tuple(plist), realm))
                plist = []
            plist.append(p)
            p = playerschain.next()
    except StopIteration:
        if plist:
            work_queue.append((tuple(plist), realm))

    return work_queue


def generate_players(xbox_start, xbox_finish, ps4_start, ps4_finish):
    '''
    Create the list of players to query for

    :param int xbox_start: Starting Xbox account ID number
    :param int xbox_finish: Ending Xbox account ID number
    :param int ps4_start: Starting PS4 account ID number
    :param int ps4_finish: Ending PS4 account ID number
    '''
    return chain(range(xbox_start, xbox_finish + 1),
                 range(ps4_start, ps4_finish + 1))


def create_config(filename):
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
        'processes': 12,
        'logging': {
            'errors': 'logs/error-%Y_%m_%d'
        },
        'database': {
            'protocol': 'mysql',
            'user': 'root',
            'password': 'password',
            'address': 'localhost',
            'name': 'battletracker'
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
        dump(newconfig, f)
