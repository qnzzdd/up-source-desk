"""采集投稿元数据（可选附带热评）。绝不下载视频、绝不读取视频内容。

用法:
    python3 -m scripts.sync_videos --limit 5
    python3 -m scripts.sync_videos --group 1 --max-pages 2 --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys

from sqlalchemy import select

from app.bili.client import BiliClient, BiliError
from app.collect import (
    Budget,
    record_failure,
    record_success,
    select_sources,
    upsert_cursor,
)
from app.config import load_settings
from app.db import init_db, session_scope
from app.models import CommentSample, Source, VideoMeta
from app.policy import CommentMode, Depth

EMOJI_RE = re.compile(r"^[\s\[\]（）()【】~～!！?？.。,，、·\-—…]+$")


def clean_comments(replies: list[dict], limit: int) -> list[str]:
    """只留正文；过滤纯表情、过短、刷屏。作者信息全部丢弃。"""
    out: list[str] = []
    seen: set[str] = set()
    for r in replies:
        text = (r.get("content") or {}).get("message") or ""
        text = re.sub(r"\[[^\]]{1,10}\]", "", text).strip()  # 去掉 [doge] 这类表情码
        if len(text) < 6 or EMOJI_RE.match(text):
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text[:200])
        if len(out) >= limit:
            break
    return out


def run(limit: int | None = None, group_id: int | None = None, max_pages: int = 1, dry_run: bool = False) -> dict:
    settings = load_settings()
    if not settings.has_cookie:
        raise SystemExit("缺少 Cookie：设置 BILI_COOKIE 或放置 cookie.txt")

    stats = {"sources": 0, "skipped_ungrouped": 0, "new_videos": 0, "comments": 0,
             "failed": 0, "paused": 0, "requests": 0}

    with BiliClient(settings) as client, session_scope() as db:
        targets = select_sources(db, group_id)
        stats["skipped_ungrouped"] = (
            db.query(Source).filter(Source.monitor_state == "ungrouped").count()
        )
        print(f"可采集 source: {len(targets)}   未分组(跳过): {stats['skipped_ungrouped']}")
        if limit:
            targets = targets[:limit]

        for src, policy in targets:
            budget = Budget(policy.max_requests_per_cycle)
            stats["sources"] += 1
            cur = upsert_cursor(db, src.id, "video", status="ok")
            last_pub = cur.last_pubdate or 0
            newest = last_pub
            try:
                for page in range(1, max_pages + 1):
                    if not budget.spend():
                        print(f"  ! {src.uname}: 达到单周期请求上限，剩余留待下轮")
                        break
                    vlist = client.list_videos(src.mid, page=page)
                    stats["requests"] += 1
                    if not vlist:
                        break
                    fresh = 0
                    for v in vlist:
                        pubdate = int(v.get("created") or 0)
                        if pubdate <= last_pub:
                            continue
                        bvid = v.get("bvid")
                        if not bvid or db.scalar(select(VideoMeta).where(VideoMeta.bvid == bvid)):
                            continue
                        db.add(
                            VideoMeta(
                                bvid=bvid,
                                aid=v.get("aid"),
                                source_id=src.id,
                                title=str(v.get("title") or ""),
                                cover_url=v.get("pic"),
                                duration=int(v.get("length") or 0) or None,
                                pubdate=pubdate,
                                view_count=int(v.get("play") or 0),
                                desc_excerpt=(v.get("description") or "")[:100] or None,
                            )
                        )
                        fresh += 1
                        newest = max(newest, pubdate)
                        stats["new_videos"] += 1

                        # L2 且触发条件满足时才拉评论
                        size = policy.comment_size_for(int(v.get("play") or 0))
                        if (
                            Depth(policy.depth).rank >= 2
                            and CommentMode(policy.comment_mode) is not CommentMode.OFF
                            and size > 0
                            and v.get("aid")
                            and budget.spend()
                        ):
                            try:
                                replies = client.top_comments(int(v["aid"]), size)
                                stats["requests"] += 1
                            except BiliError as exc:
                                print(f"  ~ {src.uname} 评论失败: {exc}")
                                replies = []
                            texts = clean_comments(replies, size)
                            if texts:
                                db.add(
                                    CommentSample(
                                        bvid=bvid,
                                        sample_size=len(texts),
                                        texts=texts,
                                    )
                                )
                                stats["comments"] += 1
                    if fresh == 0:
                        break
                upsert_cursor(db, src.id, "video", status="ok", last_pubdate=newest)
                record_success(db, src)
                print(f"  ✓ {src.uname}: 新增 {stats['new_videos']} 条累计")
            except BiliError as exc:
                stats["failed"] += 1
                if record_failure(db, src, policy, exc.kind):
                    stats["paused"] += 1
                    print(f"  ✗ {src.uname}: {exc} → 连续失败达阈值，已暂停")
                else:
                    print(f"  ✗ {src.uname}: {exc} (失败 {src.consecutive_failures}/{policy.fail_threshold})")
                upsert_cursor(db, src.id, "video", status="failed")
            if budget.exhausted:
                print("  · 预算用尽，本周期结束")
                break

        if dry_run:
            db.rollback()
            print("dry-run，已回滚")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--group", type=int, default=None)
    ap.add_argument("--max-pages", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    init_db()
    try:
        s = run(args.limit, args.group, args.max_pages, args.dry_run)
    except BiliError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 2
    print(
        f"完成：source {s['sources']}，新增投稿 {s['new_videos']}，评论采样 {s['comments']} 条视频，"
        f"失败 {s['failed']}，自动暂停 {s['paused']}，请求 {s['requests']} 次"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
