"""分组与策略管理（临时 CLI，后续由 Web 界面替代）。

    python3 -m scripts.manage groups
    python3 -m scripts.manage create "每日必看" --depth L2 --comment top10 --frequency 6h
    python3 -m scripts.manage ungrouped --limit 20
    python3 -m scripts.manage assign 12345 --group 1
    python3 -m scripts.manage policy 1 --image-mode analyze --analyze-cap 2
    python3 -m scripts.manage show 1
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

from app.db import init_db, session_scope
from app.models import Group, Source, VideoMeta
from app.policy import GroupPolicy


def fmt_group(g: Group) -> str:
    return (
        f"#{g.id:<3} {g.name:<12} {g.state:<7} {g.frequency:<5} {g.depth:<3} "
        f"comment={g.comment_mode:<5} img={g.image_mode:<8} cap={g.analyze_daily_cap} "
        f"infer={g.inference:<12} fail<={g.fail_threshold}"
    )


def cmd_groups(_args) -> int:
    with session_scope() as db:
        groups = db.scalars(select(Group).order_by(Group.sort_order, Group.id)).all()
        if not groups:
            print("还没有分组。用 create 建一个。")
            return 0
        for g in groups:
            n = db.scalar(select(func.count(Source.id)).where(Source.group_id == g.id)) or 0
            print(f"{fmt_group(g)}  源={n}")
    return 0


def cmd_create(args) -> int:
    with session_scope() as db:
        policy = GroupPolicy(
            frequency=args.frequency,
            depth=args.depth,
            comment_mode=args.comment,
            image_mode=args.image_mode,
            analyze_daily_cap=args.analyze_cap,
            inference=args.inference,
            fail_threshold=args.fail_threshold,
        )
        g = Group(name=args.name, **policy.to_dict())
        db.add(g)
        db.flush()
        print(f"已创建 {fmt_group(g)}")
    return 0


def cmd_ungrouped(args) -> int:
    with session_scope() as db:
        total = db.scalar(
            select(func.count(Source.id)).where(Source.monitor_state == "ungrouped")
        )
        rows = db.scalars(
            select(Source).where(Source.monitor_state == "ungrouped").limit(args.limit)
        ).all()
        print(f"未分组共 {total} 个，显示前 {len(rows)} 个（这些全部不采集）：")
        for s in rows:
            print(f"  {s.mid:<12} {s.uname}")
    return 0


def cmd_assign(args) -> int:
    with session_scope() as db:
        src = db.scalar(select(Source).where(Source.mid == args.mid))
        if not src:
            print(f"未找到 mid={args.mid}，先跑 sync_follows")
            return 1
        if args.group is None:
            src.group_id = None
            src.monitor_state = "ungrouped"
            print(f"{src.uname} 已退回未分组（不再采集）")
        else:
            g = db.get(Group, args.group)
            if not g:
                print(f"分组 {args.group} 不存在")
                return 1
            src.group_id = g.id
            src.monitor_state = "grouped"
            src.paused_reason = None
            src.consecutive_failures = 0
            print(f"{src.uname} → 分组「{g.name}」，策略 {g.frequency}/{g.depth}")
    return 0


def cmd_policy(args) -> int:
    fields = {
        "frequency": args.frequency,
        "depth": args.depth,
        "comment_mode": args.comment,
        "image_mode": args.image_mode,
        "analyze_daily_cap": args.analyze_cap,
        "inference": args.inference,
        "fail_threshold": args.fail_threshold,
        "state": args.state,
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    with session_scope() as db:
        g = db.get(Group, args.group_id)
        if not g:
            print("分组不存在")
            return 1
        merged = GroupPolicy(
            frequency=g.frequency, depth=g.depth, comment_mode=g.comment_mode,
            comment_trigger=g.comment_trigger, image_mode=g.image_mode,
            analyze_daily_cap=g.analyze_daily_cap, inference=g.inference,
            fail_threshold=g.fail_threshold, state=g.state,
        ).merged(fields)
        for k, v in merged.to_dict().items():
            setattr(g, k, v)
        print(f"已更新 {fmt_group(g)}")
    return 0


def cmd_show(args) -> int:
    with session_scope() as db:
        g = db.get(Group, args.group_id)
        if not g:
            print("分组不存在")
            return 1
        print(fmt_group(g))
        srcs = db.scalars(select(Source).where(Source.group_id == g.id)).all()
        print(f"源 {len(srcs)} 个：")
        for s in srcs:
            fails = s.consecutive_failures
            print(f"  {s.mid:<12} {s.uname:<20} state={s.monitor_state:<9} 连续失败={fails}")
    return 0


def cmd_stats(_args) -> int:
    with session_scope() as db:
        for label, stmt in [
            ("source 总数", select(func.count(Source.id))),
            ("未分组", select(func.count(Source.id)).where(Source.monitor_state == "ungrouped")),
            ("已分组", select(func.count(Source.id)).where(Source.monitor_state == "grouped")),
            ("已暂停", select(func.count(Source.id)).where(Source.monitor_state == "paused")),
            ("投稿元数据", select(func.count(VideoMeta.id))),
            ("分组数", select(func.count(Group.id))),
        ]:
            print(f"{label:<12} {db.scalar(stmt)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="UP源台管理 CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("groups").set_defaults(func=cmd_groups)
    sub.add_parser("stats").set_defaults(func=cmd_stats)

    c = sub.add_parser("create")
    c.add_argument("name")
    c.add_argument("--frequency", default="24h")
    c.add_argument("--depth", default="L1")
    c.add_argument("--comment", default="off")
    c.add_argument("--image-mode", default="classify")
    c.add_argument("--analyze-cap", type=int, default=1)
    c.add_argument("--inference", default="title")
    c.add_argument("--fail-threshold", type=int, default=3)
    c.set_defaults(func=cmd_create)

    u = sub.add_parser("ungrouped")
    u.add_argument("--limit", type=int, default=20)
    u.set_defaults(func=cmd_ungrouped)

    a = sub.add_parser("assign")
    a.add_argument("mid", type=int)
    a.add_argument("--group", type=int, default=None, help="省略则退回未分组")
    a.set_defaults(func=cmd_assign)

    p = sub.add_parser("policy")
    p.add_argument("group_id", type=int)
    p.add_argument("--frequency")
    p.add_argument("--depth")
    p.add_argument("--comment")
    p.add_argument("--image-mode")
    p.add_argument("--analyze-cap", type=int)
    p.add_argument("--inference")
    p.add_argument("--fail-threshold", type=int)
    p.add_argument("--state")
    p.set_defaults(func=cmd_policy)

    s = sub.add_parser("show")
    s.add_argument("group_id", type=int)
    s.set_defaults(func=cmd_show)

    args = ap.parse_args()
    init_db()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
