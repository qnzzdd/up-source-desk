"""采集公共逻辑：准入判断、预算、成功/失败记账。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Group, Source, SyncCursor
from app.policy import GroupPolicy, MonitorState, should_collect


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Budget:
    """单周期硬闸门。超预算即停止，不静默丢弃未处理项。"""

    max_requests: int
    used: int = 0
    events: list[str] = field(default_factory=list)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.max_requests

    def spend(self, n: int = 1) -> bool:
        if self.used + n > self.max_requests:
            return False
        self.used += n
        return True


def select_sources(db: Session, group_id: int | None = None) -> list[tuple[Source, GroupPolicy]]:
    """只返回真正允许采集的 source：已分组 + 分组启用。未分组一律不在结果里。"""
    stmt = select(Source, Group).join(Group, Source.group_id == Group.id, isouter=True)
    if group_id is not None:
        stmt = stmt.where(Source.group_id == group_id)
    out: list[tuple[Source, GroupPolicy]] = []
    for src, grp in db.execute(stmt).all():
        if grp is None:
            continue
        policy = GroupPolicy(
            frequency=grp.frequency,
            depth=grp.depth,
            comment_mode=grp.comment_mode,
            comment_trigger=grp.comment_trigger,
            image_mode=grp.image_mode,
            analyze_daily_cap=grp.analyze_daily_cap,
            inference=grp.inference,
            max_requests_per_cycle=grp.max_requests_per_cycle,
            max_tokens_per_cycle=grp.max_tokens_per_cycle,
            fail_threshold=grp.fail_threshold,
            state=grp.state,
        )
        if should_collect(src.monitor_state, policy):
            out.append((src, policy))
    return out


def get_cursor(db: Session, source_id: int, kind: str) -> SyncCursor | None:
    return db.scalar(
        select(SyncCursor).where(SyncCursor.source_id == source_id, SyncCursor.kind == kind)
    )


def upsert_cursor(
    db: Session,
    source_id: int,
    kind: str,
    *,
    status: str,
    last_pubdate: int | None = None,
    last_bvid: str | None = None,
) -> SyncCursor:
    cur = get_cursor(db, source_id, kind)
    if cur is None:
        cur = SyncCursor(source_id=source_id, kind=kind)
        db.add(cur)
    cur.status = status
    if last_pubdate is not None:
        cur.last_pubdate = last_pubdate
    if last_bvid is not None:
        cur.last_bvid = last_bvid
    cur.updated_at = utcnow()
    return cur


def record_success(db: Session, src: Source) -> None:
    src.consecutive_failures = 0
    src.last_success_at = utcnow()


def record_failure(db: Session, src: Source, policy: GroupPolicy, reason: str) -> bool:
    """返回是否因失败次数达到阈值而被自动暂停。"""
    src.consecutive_failures = (src.consecutive_failures or 0) + 1
    if src.consecutive_failures >= policy.fail_threshold:
        src.monitor_state = MonitorState.PAUSED.value
        src.paused_reason = "auto_fail"
        return True
    return False
