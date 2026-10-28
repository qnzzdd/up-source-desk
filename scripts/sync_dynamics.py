"""采集空间动态。图片按策略分档：分类优先，下载/分析按需。

用法:
    python3 -m scripts.sync_dynamics --limit 5 --max-pages 1 --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import httpx
from sqlalchemy import select

from app.bili.client import BiliClient, BiliError
from app.collect import Budget, record_failure, record_success, select_sources, upsert_cursor
from app.config import load_settings
from app.db import init_db, session_scope
from app.media.classify import classify
from app.models import DynamicPost, MediaAsset
from app.policy import ImageMode

MEDIA_DIR = Path("media")
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def extract(item: dict) -> dict | None:
    """把动态原始项转成扁平结构。字段缺失一律容忍。"""
    modules = item.get("modules") or {}
    author = modules.get("module_author") or {}
    dyn = modules.get("module_dynamic") or {}
    desc = (dyn.get("desc") or {}).get("text") or ""
    major = dyn.get("major") or {}
    mtype = (major.get("type") or "").upper()

    images: list[dict] = []
    video_bvid = None
    video_title = None

    if mtype == "MAJOR_TYPE_DRAW":
        images = (major.get("draw") or {}).get("items") or []
    elif mtype == "MAJOR_TYPE_OPUS":
        opus = major.get("opus") or {}
        images = opus.get("pics") or []
        desc = desc or (opus.get("summary") or {}).get("text") or ""
    elif mtype == "MAJOR_TYPE_AV":
        archive = major.get("archive") or {}
        video_bvid = archive.get("bvid")
        video_title = archive.get("title")
        desc = desc or video_title or ""

    dtype = (item.get("type") or "").upper()
    kind = "forward" if "FORWARD" in dtype else ("video_card" if video_bvid else "original")

    return {
        "dynamic_id": str(item.get("id_str") or ""),
        "kind": kind,
        "text": desc[:2000] if desc else None,
        "pubdate": int(author.get("pub_ts") or 0) or None,
        "images": images,
        "video_bvid": video_bvid,
    }


def save_image(client: BiliClient, url: str) -> tuple[str, int] | None:
    try:
        with client.http.stream("GET", url) as resp:
            resp.raise_for_status()
            h = hashlib.sha256()
            size = 0
            MEDIA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = MEDIA_DIR / ".tmp"
            with tmp.open("wb") as fh:
                for chunk in resp.iter_bytes():
                    size += len(chunk)
                    if size > MAX_IMAGE_BYTES:
                        fh.close()
                        tmp.unlink(missing_ok=True)
                        return None
                    h.update(chunk)
                    fh.write(chunk)
            digest = h.hexdigest()
            final = MEDIA_DIR / f"{digest[:16]}.img"
            tmp.replace(final)
            return digest, size
    except (httpx.HTTPError, OSError):
        return None


def run(limit: int | None = None, group_id: int | None = None, max_pages: int = 1, dry_run: bool = False) -> dict:
    settings = load_settings()
    if not settings.has_cookie:
        raise SystemExit("缺少 Cookie：设置 BILI_COOKIE 或放置 cookie.txt")

    stats = {"sources": 0, "new_posts": 0, "images_classified": 0,
             "images_downloaded": 0, "images_analyzed": 0, "failed": 0, "requests": 0}

    with BiliClient(settings) as client, session_scope() as db:
        targets = select_sources(db, group_id)
        print(f"可采集 source: {len(targets)}")
        if limit:
            targets = targets[:limit]

        for src, policy in targets:
            budget = Budget(policy.max_requests_per_cycle)
            stats["sources"] += 1
            cur = upsert_cursor(db, src.id, "dynamic", status="ok")
            newest = cur.last_pubdate or 0
            try:
                for item in client.iter_dynamics(src.mid, max_pages=max_pages):
                    if not budget.spend():
                        break
                    data = extract(item)
                    if not data or not data["dynamic_id"]:
                        continue
                    if data["pubdate"] and data["pubdate"] <= (cur.last_pubdate or 0):
                        break
                    if db.scalar(select(DynamicPost).where(DynamicPost.dynamic_id == data["dynamic_id"])):
                        continue

                    db.add(
                        DynamicPost(
                            dynamic_id=data["dynamic_id"],
                            source_id=src.id,
                            kind=data["kind"],
                            text=data["text"],
                            image_count=len(data["images"]),
                            pubdate=data["pubdate"],
                        )
                    )
                    stats["new_posts"] += 1
                    newest = max(newest, data["pubdate"] or 0)

                    # 转发不分析图片：避免把别人的内容当成该 UP 的信息
                    if data["kind"] == "forward" or ImageMode(policy.image_mode) is ImageMode.OFF:
                        continue

                    for img in data["images"]:
                        url = img.get("src") or ""
                        w, h = img.get("width"), img.get("height")
                        cls = classify(w, h, origin="dynamic")
                        digest = hashlib.sha256(url.encode()).hexdigest()
                        asset = MediaAsset(
                            image_hash=digest,
                            owner_type="dynamic",
                            owner_id=data["dynamic_id"],
                            url=url,
                            category=cls.category,
                            category_confidence=cls.confidence,
                        )
                        stats["images_classified"] += 1

                        action = policy.image_action(cls.category, 0)
                        if action in (ImageMode.DOWNLOAD.value, ImageMode.ANALYZE.value):
                            saved = save_image(client, url)
                            if saved:
                                asset.image_hash, _ = saved
                                asset.downloaded = True
                                asset.local_path = str(MEDIA_DIR / f"{saved[0][:16]}.img")
                                stats["images_downloaded"] += 1
                        # 说明：analyze 需要视觉模型端点，未配置时不伪造结果
                        db.add(asset)
                upsert_cursor(db, src.id, "dynamic", status="ok", last_pubdate=newest)
                record_success(db, src)
                print(f"  ✓ {src.uname}: 新增动态 {stats['new_posts']} 条累计")
            except BiliError as exc:
                stats["failed"] += 1
                record_failure(db, src, policy, exc.kind)
                upsert_cursor(db, src.id, "dynamic", status="failed")
                print(f"  ✗ {src.uname}: {exc}")
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
        f"完成：source {s['sources']}，新增动态 {s['new_posts']}，"
        f"图片分类 {s['images_classified']}，下载 {s['images_downloaded']}，失败 {s['failed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
