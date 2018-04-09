from datetime import datetime
import json
from sqlalchemy import Column, create_engine, event, func, DateTime, DDL
from sqlalchemy import ForeignKey, Integer, String
# from _mysql_exceptions import OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class Player(Base):
    __tablename__ = 'players'

    account_id = Column(Integer, primary_key=True)
    # Biggest I've seen is 26 thanks to the "_old_######" accounts
    nickname = Column(String(34), nullable=False)
    console = Column(String(4), nullable=False)
    created_at = Column(DateTime, nullable=False)
    last_battle_time = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    battles = Column(Integer, nullable=False)
    _last_api_pull = Column(DateTime, nullable=False)

    def __repr__(self):
        return "<Player(account_id={}, nickname='{}', console='{}', battles={})>".format(
            self.account_id,
            self.nickname,
            self.console,
            self.battles
        )


class Diff_Battles(Base):
    __tablename__ = datetime.utcnow().strftime('diff_battles_%Y_%m_%d')

    account_id = Column(
        Integer,
        ForeignKey('players.account_id'),
        primary_key=True)
    battles = Column(Integer, nullable=False)

    def __repr__(self):
        return "<Diff Battles(account_id={}, battles={})>".format(
            self.account_id, self.battles)


class Total_Battles(Base):
    __tablename__ = datetime.utcnow().strftime('total_battles_%Y_%m_%d')

    account_id = Column(
        Integer,
        ForeignKey('players.account_id'),
        primary_key=True)
    battles = Column(Integer, nullable=False)

    def __repr__(self):
        return "<Total Battles(account_id={}, battles={})>".format(
            self.account_id, self.battles)


def setup_trigger(db):
    r"""
    When player battle values are updated, create new records in today's
    diff_battle table
    """
    engine = create_engine(
        "{protocol}://{user}:{password}@{address}/{name}".format(**db),
        echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()
    battle_ddl = DDL("""
        CREATE TRIGGER update_battles BEFORE UPDATE ON players
        FOR EACH ROW
        BEGIN
            IF (OLD.battles < NEW.battles) THEN
                INSERT INTO {} VALUES (NEW.account_id, NEW.battles);
                INSERT INTO {} VALUES (NEW.account_id, NEW.battles - OLD.battles);
            END IF;
        END
    """.format(Total_Battles.__tablename__, Diff_Battles.__tablename__))
    event.listen(
        Player.__table__,
        'after_create',
        battle_ddl.execute_if(
            dialect='mysql'))
    newplayer_ddl = DDL("""
        CREATE TRIGGER new_player AFTER INSERT ON players
        FOR EACH ROW INSERT INTO {} VALUES (NEW.account_id, NEW.battles);
    """.format(Total_Battles.__tablename__))
    event.listen(
        Player.__table__,
        'after_create',
        newplayer_ddl.execute_if(
            dialect='mysql'))
    Base.metadata.create_all(engine)
    session.execute("""
        DROP TRIGGER IF EXISTS new_player;
        DROP TRIGGER IF EXISTS update_battles;
    """)
    session.execute(battle_ddl)
    session.execute(newplayer_ddl)
    session.commit()


def expand_max_players(config, filename='./config/server.json'):
    dbconf = config['database']
    update = False
    engine = create_engine(
        "{protocol}://{user}:{password}@{address}/{name}".format(**dbconf),
        echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()
    max_xbox = int(session.query(Player, func.max(Player.account_id)
                                 ).filter(Player.console == 'xbox').one()[1])
    max_ps4 = int(session.query(Player, func.max(Player.account_id)
                                ).filter(Player.console == 'ps4').one()[1])
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
