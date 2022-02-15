import asyncpg
from datetime import datetime, timedelta
import json

MASTER_COLUMNS = {
    'account_id': 'integer NOT NULL',
    'nickname': 'varchar(34) NOT NULL',
    'created_at': 'timestamp NOT NULL',
    'last_battle_time': 'timestamp NOT NULL',
    'updated_at': 'timestamp NOT NULL',
    'battles': 'integer NOT NULL',
    'console': 'varchar(4) NOT NULL',
    'spotted': 'integer',
    'wins': 'integer',
    'damage_dealt': 'integer',
    'frags': 'integer',
    'dropped_capture_points': 'integer',
    '_last_api_pull': 'timestamp NOT NULL'
}

SERIES_COLUMNS = {
    'account_id': 'integer NOT NULL',
    'battles': 'integer',
    'console': 'varchar(4)',
    'spotted': 'integer',
    'wins': 'integer',
    'damage_dealt': 'integer',
    'frags': 'integer',
    'dropped_capture_points': 'integer',
    '_date': 'date NOT NULL'
}

async def add_missing_columns(conn, table, schema):
    columns = await conn.fetch(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'")
    columns = list(column['column_name'] for column in columns)
    for column, definition in schema.items():
        if column not in columns:
            __ = await conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')


async def setup_database(db, use_temp=False):
    now = datetime.now()
    conn = await asyncpg.connect(**db)
    __ = await conn.execute('''
        CREATE TABLE IF NOT EXISTS players (
            account_id integer PRIMARY KEY,
            nickname varchar(34) NOT NULL,
            console varchar(4) NOT NULL,
            created_at timestamp NOT NULL,
            last_battle_time timestamp NOT NULL,
            updated_at timestamp NOT NULL,
            battles integer NOT NULL,
            spotted integer NOT NULL,
            wins integer NOT NULL,
            damage_dealt integer NOT NULL,
            frags integer NOT NULL,
            dropped_capture_points integer NOT NULL,
            _last_api_pull timestamp NOT NULL)''')

    __ = await add_missing_columns(conn, 'players', MASTER_COLUMNS)

    if use_temp:
        __ = await conn.execute('DROP TABLE IF EXISTS temp_players')

        __ = await conn.execute('''
            CREATE TABLE temp_players (
                account_id integer PRIMARY KEY,
                nickname varchar(34) NOT NULL,
                console varchar(4) NOT NULL,
                created_at timestamp NOT NULL,
                last_battle_time timestamp NOT NULL,
                updated_at timestamp NOT NULL,
                battles integer NOT NULL,
                spotted integer NOT NULL,
                wins integer NOT NULL,
                damage_dealt integer NOT NULL,
                frags integer NOT NULL,
                dropped_capture_points integer NOT NULL,
                _last_api_pull timestamp NOT NULL)''')

    # Cannot set new columns to NOT NULL until data is retroactively added
    __ = await conn.execute('''
        CREATE TABLE IF NOT EXISTS total_battles
        (
            account_id integer NOT NULL,
            battles integer,
            console varchar(4),
            spotted integer,
            wins integer,
            damage_dealt integer,
            frags integer,
            dropped_capture_points integer,
            _date date NOT NULL
        ) PARTITION BY RANGE (_date);

        CREATE UNIQUE INDEX IF NOT EXISTS total_battles_account_id_idx
            ON total_battles USING btree (account_id, _date);
        ''')

    __ = await add_missing_columns(conn, 'total_battles', SERIES_COLUMNS)

    __ = await conn.execute('''
        CREATE TABLE IF NOT EXISTS diff_battles
        (
            account_id integer NOT NULL,
            tank_id integer,
            battles integer,
            console varchar(4),
            spotted integer,
            wins integer,
            damage_dealt integer,
            frags integer,
            dropped_capture_points integer,
            _date date NOT NULL
        ) PARTITION BY RANGE (_date);

        CREATE UNIQUE INDEX IF NOT EXISTS diff_battles_account_id_idx
            ON diff_battles USING btree (account_id, _date);
        ''')

    __ = await add_missing_columns(conn, 'diff_battles', SERIES_COLUMNS)

    # Cannot set new columns to NOT NULL until data is retroactively added
    __ = await conn.execute('''
        CREATE TABLE {}
        PARTITION OF total_battles
        FOR VALUES FROM ('{}') TO ('{}')
        '''.format(
            (now - timedelta(days=1)).strftime('total_battles_%Y_%m_%d'),
            (now - timedelta(days=1)).strftime('%Y-%m-%d'),
            now.strftime('%Y-%m-%d')
        )
    )

    # Cannot set new columns to NOT NULL until data is retroactively added
    __ = await conn.execute('''
        CREATE TABLE {}
        PARTITION OF diff_battles
        FOR VALUES FROM ('{}') TO ('{}')
        '''.format(
            (now - timedelta(days=1)).strftime('diff_battles_%Y_%m_%d'),
            (now - timedelta(days=1)).strftime('%Y-%m-%d'),
            now.strftime('%Y-%m-%d')
        )
    )

    # We shouldn't get a duplicate error because of the REPLACE statement
    try:
        __ = await conn.execute('''
            CREATE OR REPLACE FUNCTION update_total()
              RETURNS trigger AS
            $func$
            BEGIN
              IF (OLD.battles < NEW.battles) THEN
                EXECUTE 'INSERT INTO total_battles ('
                  'account_id, battles, console, spotted, wins, damage_dealt, '
                  'frags, dropped_capture_points, _date'
                  ') VALUES ('
                  '$1.account_id, $1.battles, $1.console, $1.spotted, $1.wins, '
                  '$1.damage_dealt, $1.frags, $1.dropped_capture_points, (now() - INTERVAL ''1 DAY'')::date) '
                  'ON CONFLICT DO NOTHING' USING NEW;
                EXECUTE 'INSERT INTO diff_battles ('
                  'account_id, battles, console, spotted, wins, damage_dealt, '
                  'frags, dropped_capture_points, _date'
                  ') VALUES ('
                  '$1.account_id, $1.battles - $2.battles, $1.console, '
                  '$1.spotted - $2.spotted, $1.wins - $2.wins, '
                  '$1.damage_dealt - $2.damage_dealt, $1.frags - $2.frags, '
                  '$1.dropped_capture_points - $2.dropped_capture_points, (now() - INTERVAL ''1 DAY'')::date) '
                  'ON CONFLICT DO NOTHING' USING NEW, OLD;
              END IF;
              RETURN NEW;
            END
            $func$ LANGUAGE plpgsql;''')
    except asyncpg.exceptions.DuplicateObjectError:
        pass

    try:
        __ = await conn.execute('CREATE TRIGGER update_stats BEFORE UPDATE ON players FOR EACH ROW EXECUTE PROCEDURE update_total();')
    except asyncpg.exceptions.DuplicateObjectError:
        pass

    # We shouldn't get a duplicate error because of the REPLACE statement.
    # Why do we insert into diff_battles_*? If the player is brand new, then their previous total battle count is 0. We want to include their battles too in each day's count
    try:
        __ = await conn.execute('''
            CREATE OR REPLACE FUNCTION new_player()
              RETURNS trigger AS
            $func$
            BEGIN
              EXECUTE 'INSERT INTO total_battles ('
                'account_id, battles, console, spotted, wins, damage_dealt, '
                'frags, dropped_capture_points, _date'
                ') VALUES ('
                '$1.account_id, $1.battles, $1.console, $1.spotted, $1.wins, '
                '$1.damage_dealt, $1.frags, $1.dropped_capture_points, (now() - INTERVAL ''1 DAY'')::date) '
                'ON CONFLICT DO NOTHING' USING NEW;
              IF (NEW.battles > 0) THEN
                EXECUTE 'INSERT INTO diff_battles ('
                  'account_id, battles, console, spotted, wins, damage_dealt, '
                  'frags, dropped_capture_points, _date'
                  ') VALUES ('
                  '$1.account_id, $1.battles, $1.console, $1.spotted, $1.wins, '
                  '$1.damage_dealt, $1.frags, $1.dropped_capture_points, (now() - INTERVAL ''1 DAY'')::date) '
                  'ON CONFLICT DO NOTHING' USING NEW;
              END IF;
              RETURN NEW;
            END
            $func$ LANGUAGE plpgsql;''')
    except asyncpg.exceptions.DuplicateObjectError:
        pass

    try:
        __ = await conn.execute('CREATE TRIGGER new_player_total AFTER INSERT ON players FOR EACH ROW EXECUTE PROCEDURE new_player();')
    except asyncpg.exceptions.DuplicateObjectError:
        pass


async def expand_max_players(config, filename='./config/server.json'):
    dbconf = config['database']
    update = False

    conn = await asyncpg.connect(**dbconf)

    for platform in ('xbox', 'ps4'):
        try:
            maximum = await conn.fetch(
                'SELECT MAX(account_id) FROM players WHERE account_id BETWEEN $1 AND $2',
                config[platform]['max account'] - 50000,
                config[platform]['max account']
            )
            for record in maximum:
                if platform == 'xbox':
                    max_xbox = record['max']
                else:
                    max_ps4 = record['max']
        except KeyError:
            pass

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
