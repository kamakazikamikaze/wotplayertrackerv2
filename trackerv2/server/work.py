
def setup_work(config):
    r"""
    Create the initial player groups for workers to query

    Work is stored in the format of (batch id, tuple(player start ID, player
    end ID), realm)

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
        
    constraints = (
        (xbox_start_account, xbox_max_account, 'xbox'),
        (ps4_start_account, ps4_max_account, 'ps4')
    )
    for start, end, console in constraints:
        for p in range(start, end, 100):
            batch_id += 1
            yield (batch_id, (p, p+100), console)
