from itertools import chain


def setup_work(config):
    r"""
    Create the initial player groups for workers to query

    Work is stored in the format of (batch id, tuple(player IDs), realm)

    :yields: Work batch
    """
    batch_id = 0
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

    constraints = (('xbox', xbox_max_account), ('ps4', ps4_max_account))
    plist = []
    # p = playerschain.next()
    p = next(playerschain)
    for realm, max_account in constraints:
        try:
            while p <= max_account:
                if len(plist) == 100:
                    batch_id += 1
                    yield (batch_id, tuple(plist), realm)
                    plist = []
                plist.append(p)
                # p = playerschain.next()
                p = next(playerschain)
            if plist:
                batch_id += 1
                yield (batch_id, tuple(plist), realm)
        except StopIteration:
            if plist:
                batch_id += 1
                yield (batch_id, tuple(plist), realm)


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
