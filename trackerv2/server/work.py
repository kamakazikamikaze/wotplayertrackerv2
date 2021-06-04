
from constants import XBOX_MIN, XBOX_MAX, PS4_MIN, PS4_MAX


def setup_work(config):
    r"""
    Create the initial player groups for workers to query

    Work is stored in the format of (batch id, tuple(player start ID, player
    end ID), realm)

    :yields: Work batch
    """
    batch_id = 0
    xbox_start_account = XBOX_MIN if 'start account' not in config[
        'xbox'] else config['xbox']['start account']
    xbox_max_account = XBOX_MAX if 'max account' not in config[
        'xbox'] else config['xbox']['max account']
    ps4_start_account = PS4_MIN if 'start account' not in config[
        'ps4'] else config['ps4']['start account']
    ps4_max_account = PS4_MAX if 'max account' not in config[
        'ps4'] else config['ps4']['max account']

    constraints = (
        (xbox_start_account, xbox_max_account),
        (ps4_start_account, ps4_max_account)
    )
    for start, end in constraints:
        for p in range(start, end, 100):
            batch_id += 1
            yield (batch_id, (p, p + 100))


def calculate_total_batches(config):
    r"""
    Helper function to calculate the total number of batches to query

    :returns: Total count of 100-player batches
    """
    xbox_start_account = XBOX_MIN if 'start account' not in config[
        'xbox'] else config['xbox']['start account']
    xbox_max_account = XBOX_MAX if 'max account' not in config[
        'xbox'] else config['xbox']['max account']
    ps4_start_account = PS4_MIN if 'start account' not in config[
        'ps4'] else config['ps4']['start account']
    ps4_max_account = PS4_MAX if 'max account' not in config[
        'ps4'] else config['ps4']['max account']

    # Negation to convert floor division to ceiling division
    return (
        -(-(xbox_max_account - xbox_start_account) // 100) +
        (-(-(ps4_max_account - ps4_start_account) // 100))
    )
