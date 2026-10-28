from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.collect import Budget, record_failure, select_sources
from app.models import Base, Group, Source
from app.policy import GroupPolicy


def make_db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def add_group(db: Session, **kw) -> Group:
    g = Group(name=kw.pop("name", "g"), **GroupPolicy().to_dict())
    for k, v in kw.items():
        setattr(g, k, v)
    db.add(g)
    db.commit()
    return g


def test_ungrouped_source_is_not_selected():
    with make_db() as db:
        db.add(Source(mid=1, uname="a", monitor_state="ungrouped"))
        db.commit()
        assert select_sources(db) == []


def test_grouped_source_is_selected():
    with make_db() as db:
        g = add_group(db, name="g1")
        db.add(Source(mid=2, uname="b", group_id=g.id, monitor_state="grouped"))
        db.commit()
        rows = select_sources(db)
        assert len(rows) == 1 and rows[0][0].mid == 2
        assert rows[0][1].depth == "L1"


def test_paused_group_is_not_selected():
    with make_db() as db:
        g = add_group(db, name="g2", state="paused")
        db.add(Source(mid=3, uname="c", group_id=g.id, monitor_state="grouped"))
        db.commit()
        assert select_sources(db) == []


def test_paused_source_is_not_selected():
    with make_db() as db:
        g = add_group(db, name="g3")
        db.add(Source(mid=4, uname="d", group_id=g.id, monitor_state="paused"))
        db.commit()
        assert select_sources(db) == []


def test_fail_threshold_pauses_source():
    with make_db() as db:
        g = add_group(db, name="g4", fail_threshold=3)
        src = Source(mid=5, uname="e", group_id=g.id, monitor_state="grouped")
        db.add(src)
        db.commit()
        policy = GroupPolicy(fail_threshold=3)
        assert record_failure(db, src, policy, "network") is False
        assert record_failure(db, src, policy, "network") is False
        assert record_failure(db, src, policy, "network") is True
        assert src.monitor_state == "paused" and src.paused_reason == "auto_fail"


def test_budget_never_exceeds_limit():
    b = Budget(max_requests=3)
    assert b.spend() and b.spend() and b.spend()
    assert b.exhausted
    assert b.spend() is False
    assert b.used == 3
