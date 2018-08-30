import asyncpg
from datetime import datetime
import json


async def setup_database(db):
    conn = await asyncpg.connect(**db)
    _ = await conn.execute('''
        CREATE TABLE IF NOT EXISTS players (
            account_id integer PRIMARY KEY,
            nickname varchar(34) NOT NULL,
            console varchar(4) NOT NULL,
            created_at timestamp NOT NULL,
            last_battle_time timestamp NOT NULL,
            updated_at timestamp NOT NULL,
            battles integer NOT NULL,
            _last_api_pull timestamp NOT NULL)''')

    _ = await conn.execute('''
        CREATE TABLE {} (
        account_id integer PRIMARY KEY REFERENCES players (account_id),
        battles integer NOT NULL)'''.format(datetime.utcnow().strftime('total_battles_%Y_%m_%d')))

    _ = await conn.execute('''
        CREATE TABLE {} (
        account_id integer PRIMARY KEY REFERENCES players (account_id),
        battles integer NOT NULL)'''.format(datetime.utcnow().strftime('diff_battles_%Y_%m_%d')))

    try:
        _ = await conn.execute('''
            CREATE OR REPLACE FUNCTION update_total()
              RETURNS trigger AS
            $func$
            BEGIN
               IF (OLD.battles < NEW.battles) THEN
                  EXECUTE format('INSERT INTO total_battles_%s (account_id, battles) VALUES ($1.account_id, $1.battles)', to_char(timezone('UTC'::text, now()), 'YYYY_MM_DD')) USING NEW;
                  EXECUTE format('INSERT INTO diff_battles_%s (account_id, battles) VALUES ($1.account_id, $1.battles - $2.battles)', to_char(timezone('UTC'::text, now()), 'YYYY_MM_DD')) USING NEW, OLD;
               END IF;
               RETURN NEW;
            END
            $func$ LANGUAGE plpgsql;
            CREATE TRIGGER update_stats BEFORE UPDATE ON players FOR EACH ROW EXECUTE PROCEDURE update_total();''')
    except asyncpg.exceptions.DuplicateObjectError:
        pass

    try:
        _ = await conn.execute('''
            CREATE OR REPLACE FUNCTION new_player()
              RETURNS trigger AS
            $func$
            BEGIN
              EXECUTE format('INSERT INTO total_battles_%s (account_id, battles) VALUES ($1.account_id, $1.battles)', to_char(timezone('UTC'::text, now()), 'YYYY_MM_DD')) USING NEW;
              RETURN NEW;
            END
            $func$ LANGUAGE plpgsql;
            CREATE TRIGGER new_player_total AFTER INSERT ON players FOR EACH ROW EXECUTE PROCEDURE new_player();''')
    except asyncpg.exceptions.DuplicateObjectError:
        pass


async def expand_max_players(config, filename='./config/server.json'):
    dbconf = config['database']
    update = False

    conn = await asyncpg.connect(**dbconf)

    maximum = await conn.fetch(
        'SELECT MAX(account_id), console FROM players GROUP BY console'
    )
    for record in maximum:
        if record['console'] == 'xbox':
            max_xbox = record['max']
        else:
            max_ps4 = record['max']

    if 'max account' not in config['xbox']:
        config['xbox']['max account'] = max_xbox + 200000
        update = True
    elif config['xbox']['max account'] - max_xbox < 50000:
        config['xbox']['max account'] += 100000
        update = True
    if 'max account' not in config['ps4']:
        config['ps4']['max account'] = max_ps4 + 200000
        update = True
    elif config['ps4']['max account'] - max_ps4 < 50000:
        config['ps4']['max account'] += 100000
        update = True

    if update:
        if 'debug' in config and config['debug']:
            print('Updating configuration.')
            print('Max Xbox account:', max_xbox)
            print('Max PS4 account:', max_ps4)
        with open(filename, 'w') as f:
            json.dump(config, f)
