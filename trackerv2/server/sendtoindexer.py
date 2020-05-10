from elasticsearch import Elasticsearch, helpers
from elasticsearch import TransportError, ConnectionTimeout
from elasticsearch.helpers import BulkIndexError
import json
from uuid import uuid4
from os import makedirs, path, remove, pardir
import pickle
from types import AsyncGeneratorType, GeneratorType


def check_index(conf):
    pass


def create_index(conf):
    pass


async def send_data(conf, data, action='create'):
    r"""
    Send data to Elasticsearch cluster(s)
    :param dict conf: Full configuration
    :param list(dict) data: All ES docs to send
    """
    for name, cluster in conf['elasticsearch']['clusters'].items():
        try:
            if action == 'create':
                await _send_to_cluster(cluster, data)
            elif action == 'update':
                await _update_to_cluster(cluster, data)
        except (BulkIndexError, TransportError) as err:
            print('ES: Error encountered. Offloading data.')
            print('ES: Error:', err)
            await offload_local(
                name,
                cluster,
                conf['elasticsearch']['offload'],
                data)


async def _send_to_cluster(conf, data):
    r"""
    Stream data to an Elasticsearch cluster.
    .. note: This method does **not** catch exceptions
    :param dict conf: Connection parameters for `elasticsearch.Elasticsearch`
    :param list(dict) data: ES documents to send
    """
    es = Elasticsearch(**conf)
    if isinstance(data, GeneratorType):
        data = list(data)
    elif isinstance(data, AsyncGeneratorType):
        data = [d async for d in data]
    helpers.bulk(es, data)


async def _send_to_cluster_skip_errors(conf, data, retry=5):
    r"""
    Stream data to an Elasticsearch cluster.
    :param dict conf: Connection parameters for `elasticsearch.Elasticsearch`
    :param list(dict) data: ES documents to send
    :param int retry: Number of times to retry sending a batch if error occurs
    """
    def chunks(l, n):
        n = max(1, n)
        return (l[i:i + n] for i in range(0, len(l), n))
    es = Elasticsearch(**conf)
    if isinstance(data, GeneratorType):
        data = list(data)
    elif isinstance(data, AsyncGeneratorType):
        data = [d async for d in data]
    for chunk in chunks(data, 100):
        attempts = retry
        while attempts:
            try:
                helpers.bulk(es, chunk)
                break
            except:
                attempts -= 1


async def _update_to_cluster(conf, data):
    es = Elasticsearch(**conf)
    if isinstance(data, GeneratorType):
        for doc in data:
            try:
                es.update(
                    index=doc['_index'],
                    doc_type=doc['_type'],
                    id=doc['_id'],
                    body={'doc': doc['_source']}
                )
            except TransportError as te:
                if te.args[1] == 'document_missing_exception':
                    helpers.bulk(es, [doc])
                else:
                    raise te
    elif isinstance(data, AsyncGeneratorType):
        async for doc in data:
            try:
                es.update(
                    index=doc['_index'],
                    doc_type=doc['_type'],
                    id=doc['_id'],
                    body={'doc': doc['_source']})
            except TransportError as te:
                if te.args[1] == 'document_missing_exception':
                    helpers.bulk(es, [doc])
                else:
                    raise te


async def offload_local(name, clusterconf, dumpconf, data):
    r"""
    When the Elasticsearch cluster/node is unavailable, offload data to disk
    and try to resend the next time the script is run.
    :param str name: Cluster (nick)name
    :param dict clusterconf: Connection configuration for the cluster
    :param dict dumpconf: `configuration['elasticsearch']['offload']`
    :param list(dict) data: All ES documents to be flushed to disk
    """
    dumpuuid = str(uuid4())
    if not path.exists(dumpconf['data folder']):
        makedirs(dumpconf['data folder'])
    with open(path.join(dumpconf['data folder'], dumpuuid), 'wb') as outfile:
        if isinstance(data, GeneratorType):
            data = list(data)
        elif isinstance(data, AsyncGeneratorType):
            data = [d async for d in data]
        pickle.dump(data, outfile, pickle.HIGHEST_PROTOCOL)
    # with open(conf['index'], 'a') as indexfile:
    #     indexfile.write(dumpuuid + '\n')
    if path.exists(dumpconf['index']):
        with open(dumpconf['index']) as f:
            indexdata = json.load(f)
    else:
        if not path.exists(path.abspath(path.join(dumpconf['index'], pardir))):
            makedirs(path.abspath(path.join(dumpconf['index'], pardir)))
        indexdata = {'clusters': {}, 'dumps': {}}
    if name not in indexdata['clusters']:
        indexdata['clusters'][name] = clusterconf
        indexdata['dumps'][name] = []
    indexdata['dumps'][name].append(dumpuuid)
    with open(dumpconf['index'], 'w') as f:
        json.dump(indexdata, f)


def load_local(conf):
    r"""
    Check if Elasticsearch clusters are online and attempt to send data.
    :param dict conf: `configuration['elasticsearch']['offload']`
    """
    with open(conf['index']) as f:
        indexdata = json.load(f)
    for name, cluster in indexdata['clusters'].items():
        success = set()
        for dump in indexdata['dumps'][name]:
            with open(path.join(conf['data folder'], dump), 'rb') as f:
                data = pickle.load(f)
            try:
                if conf['delete old index on reload']:
                    es = Elasticsearch(**cluster)
                    es.indices.delete(
                        data[0]['_index'], ignore_unavailable=True)
                _send_to_cluster(cluster, data)
                success.add(dump)
                remove(path.join(conf['data folder'], dump))
            except BulkIndexError:
                pass
            except TransportError:
                # Cannot reach. Skip
                break
        indexdata['dumps'][name] = list(
            set(indexdata['dumps'][name]) - success)
    with open(conf['index'], 'w') as f:
        json.dump(indexdata, f)


# generators
def create_generator_totals(day, query_results):
    return ({
        "_index": day.strftime("total_battles-%Y.%m.%d"),
        "_type": "total",
        "_id": player['account_id'],
        "_source": {
            "account_id": player['account_id'],
            "battles": player['battles'],
            "date": day.strftime("%Y-%m-%d")
        }
    } for player in query_results)


def create_generator_diffs(day, query_results):
    return ({
        "_index": day.strftime("diff_battles-%Y.%m.%d"),
        "_type": "diff",
        "_id": player['account_id'],
        "_source": {
            "account_id": player['account_id'],
            "battles": player['battles'],
            "date": day.strftime("%Y-%m-%d")
        }
    } for player in query_results)


async def create_generator_players(statement, player_ids):
    for pid in player_ids:
        player = await statement.fetchrow(pid)
        yield {
            "_index": "players",
            "_type": "player",
            "_id": player['account_id'],
            "_source": {
                "account_id": player['account_id'],
                "nickname": player['nickname'],
                "console": player['console'],
                "created_at": player['created_at'],
                "last_battle_time": player['last_battle_time'],
                "updated_at": player['updated_at'],
                "battles": player['battles'],
                "last_api_pull": player['_last_api_pull']
            }
        }


def create_generator_players_sync(query_results):
    return ({
        "_index": "players",
        "_type": "player",
        "_id": player['account_id'],
        "_source": {
            "account_id": player['account_id'],
            "nickname": player['nickname'],
            "console": player['console'],
            "created_at": player['created_at'],
            "last_battle_time": player['last_battle_time'],
            "updated_at": player['updated_at'],
            "battles": player['battles'],
            "last_api_pull": player['_last_api_pull']
        }
    } for player in query_results)
