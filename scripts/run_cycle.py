"""按分组策略跑一个采集周期。可挂到 Windows 任务计划里每分钟触发一次，
未到频率的分组会被跳过，所以触发频率高一点也没关系。

用法:
    python3 -m scripts.run_cycle --dry-run
    python3 -m scripts.run_cycle --force
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.bili.client import BiliError
from app.config import load_settings
from app.db import init_db, session_scope
from app.models import Group, JobRun
from app.policy import Frequency, GroupState
import scripts.sync_dynamics as dyn
import scripts.sync_videos as vid


def last_run(db, group_id: int) -> datetime | None:
    row = db.scalars(
        select(JobRun)
        .where(JobRun.kind == f"cycle:{group_id}", JobRun.status == "ok")
        .order_by(JobRun.started_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    ts = row.started_at
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def is_due(db, group: Group, force: bool) -> bool:
    if group.state != GroupState.ACTIVE.value:
        return False
    secs = Frequency(group.frequency).seconds
    if secs is None:  # manual：只由人工触发
        return force
    if force:
        return True
    prev = last_run(db, group.id)
    if prev is None:
        return True
    return (datetime.now(timezone.utc) - prev).total_seconds() >= secs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="忽略频率限制")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="每组最多处理多少个 source")
    ap.add_argument("--max-pages", type=int, default=1)
    args = ap.parse_args()

    init_db()
    settings = load_settings()
    if not settings.has_cookie:
        print("缺少 Cookie：设置 BILI_COOKIE 或放置 cookie.txt", file=sys.stderr)
        return 1

    with session_scope() as db:
        groups = db.scalars(select(Group).order_by(Group.sort_order, Group.id)).all()
        due = [g for g in groups if is_due(db, g, args.force)]
        for g in groups:
            mark = "跑" if g in due else "跳过"
            print(f"[{mark}] #{g.id} {g.name} ({g.frequency}/{g.depth}/{g.state})")

    if not due:
        print("没有到期的分组。")
        return 0

    total = {"v": 0, "d": 0, "fail": 0}
    for g in due:
        job = JobRun(kind=f"cycle:{g.id}", status="running")
        with session_scope() as db:
            db.add(job)
            db.flush()
            job_id = job.id
        status, msg = "ok", ""
        try:
            print(f"\n== 分组 {g.name} · 投稿 ==")
            sv = vid.run(limit=args.limit, group_id=g.id, max_pages=args.max_pages, dry_run=args.dry_run)
            total["v"] += sv["new_videos"]
            print(f"== 分组 {g.name} · 动态 ==")
            sd = dyn.run(limit=args.limit, group_id=g.id, max_pages=args.max_pages, dry_run=args.dry_run)
            total["d"] += sd["new_posts"]
            total["fail"] += sv["failed"] + sd["failed"]
        except BiliError as exc:
            status, msg = "failed", str(exc)
            print(f"分组 {g.name} 失败：{exc}", file=sys.stderr)
        finally:
            with session_scope() as db:
                j = db.get(JobRun, job_id)
                j.status = status
                j.message = msg
                j.finished_at = datetime.now(timezone.utc)

    print(f"\n本周期：新增投稿 {total['v']}，新增动态 {total['d']}，失败 {total['fail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
