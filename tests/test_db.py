from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, Group, Source


def make_session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_new_source_defaults_to_ungrouped():
    with make_session() as db:
        db.add(Source(mid=1, uname="someone"))
        db.commit()
        src = db.scalar(select(Source))
        assert src.group_id is None
        assert src.monitor_state == "ungrouped"


def test_group_policy_columns_have_defaults():
    with make_session() as db:
        db.add(Group(name="每日必看"))
        db.commit()
        g = db.scalar(select(Group))
        assert g.frequency == "24h"
        assert g.depth == "L1"
        assert g.analyze_daily_cap == 1
        assert g.fail_threshold == 3
        assert g.state == "active"


def test_uname_history_unique():
    from app.models import SourceNameHistory

    with make_session() as db:
        src = Source(mid=2, uname="a")
        db.add(src)
        db.flush()
        db.add(SourceNameHistory(source_id=src.id, uname="a"))
        db.commit()
        assert db.scalar(select(SourceNameHistory)).uname == "a"
