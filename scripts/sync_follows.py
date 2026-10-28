"""同步关注列表。只发现，不采集内容。

用法:
    BILI_COOKIE="SESSDATA=..." python3 -m scripts.sync_follows --limit 100
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.bili.client import BiliClient, BiliError
from app.config import load_settings
from app.db import init_db, session_scope
from app.models import Source, SourceNameHistory, utcnow


def sync(limit: int | None = None, dry_run: bool = False) -> dict:
    settings = load_settings()
    if not settings.has_cookie:
        raise SystemExit(
            "缺少 Cookie。请设置环境变量 BILI_COOKIE，或在项目根目录放 cookie.txt（勿提交）。"
        )

    stats = {"total": 0, "new_ungrouped": 0, "renamed": 0, "unfollowed": 0}
    seen_mids: set[int] = set()

    with BiliClient(settings) as client, session_scope() as db:
        print(f"登录账号 mid = {client.self_mid}")
        for row in client.iter_followings():
            mid = int(row["mid"])
            uname = str(row.get("uname") or "")
            seen_mids.add(mid)
            stats["total"] += 1
            if limit and stats["total"] > limit:
                break

            src = db.scalar(select(Source).where(Source.mid == mid))
            if src is None:
                # 新增关注：一律 ungrouped，不发起任何内容采集
                src = Source(
                    mid=mid,
                    uname=uname,
                    face=row.get("face"),
                    sign=row.get("sign"),
                    monitor_state="ungrouped",
                    last_synced_at=utcnow(),
                )
                db.add(src)
                db.flush()
                db.add(SourceNameHistory(source_id=src.id, uname=uname))
                stats["new_ungrouped"] += 1
            else:
                if src.uname != uname:
                    src.name_history.append(SourceNameHistory(uname=uname))
                    stats["renamed"] += 1
                src.uname = uname
                src.face = row.get("face") or src.face
                src.is_followed = True
                src.last_synced_at = utcnow()

        if not limit:
            followed = db.scalars(select(Source).where(Source.is_followed.is_(True))).all()
            for src in followed:
                if src.mid not in seen_mids:
                    src.is_followed = False
                    stats["unfollowed"] += 1

        if dry_run:
            db.rollback()
            print("dry-run，已回滚")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 个，用于试跑")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--init-db", action="store_true", help="只建表然后退出")
    args = ap.parse_args()

    init_db()
    if args.init_db:
        print("已建表")
        return 0

    try:
        stats = sync(limit=args.limit, dry_run=args.dry_run)
    except BiliError as exc:
        print(f"同步失败：{exc}", file=sys.stderr)
        return 2
    print(
        f"完成：共 {stats['total']} 人，新增未分组 {stats['new_ungrouped']}，"
        f"改名 {stats['renamed']}，取关 {stats['unfollowed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
