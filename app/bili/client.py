"""B 站只读客户端：关注列表、投稿元数据。

约定：仅使用登录态做只读请求；串行 + 间隔 + 指数退避；不打印 Cookie。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterator

import httpx

from app.bili import wbi
from app.config import Settings

API = "https://api.bilibili.com"


class BiliError(RuntimeError):
    def __init__(self, code: int, message: str, kind: str = "api"):
        super().__init__(f"[{kind}] code={code} {message}")
        self.code = code
        self.message = message
        self.kind = kind


@dataclass
class RateLimit:
    interval: float = 1.0
    _last: float = 0.0

    def wait(self) -> None:
        gap = self.interval - (time.monotonic() - self._last)
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()


class BiliClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.rate = RateLimit(settings.request_interval)
        self._wbi: tuple[str, str] | None = None
        headers = {"User-Agent": settings.user_agent, "Referer": "https://www.bilibili.com/"}
        if settings.cookie:
            headers["Cookie"] = settings.cookie
        self.http = client or httpx.Client(headers=headers, timeout=15.0, follow_redirects=True)
        self._mid: int | None = None

    # --- 基础请求 ---

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "BiliClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, path: str, params: dict | None = None, *, signed: bool = False) -> dict:
        params = dict(params or {})
        if signed:
            img_key, sub_key = self._wbi_keys()
            params = wbi.sign(params, img_key, sub_key)
        last_err: Exception | None = None
        for attempt in range(1, self.settings.max_retries + 1):
            self.rate.wait()
            try:
                resp = self.http.get(API + path, params=params)
                if resp.status_code in (412, 429):
                    raise BiliError(resp.status_code, "被限流或触发风控", "ratelimit")
                resp.raise_for_status()
                payload = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_err = exc
                time.sleep(min(2 ** attempt, 10))
                continue
            code = payload.get("code", 0)
            if code == 0:
                return payload
            if code in (-101, -111):  # 未登录 / csrf 失效
                raise BiliError(code, payload.get("message", "未登录或登录已失效"), "auth")
            if code == -352:  # 风控
                raise BiliError(code, payload.get("message", "风控校验"), "ratelimit")
            raise BiliError(code, payload.get("message", "接口返回错误"))
        raise BiliError(0, f"请求失败: {last_err}", "network")

    def _wbi_keys(self) -> tuple[str, str]:
        if self._wbi is None:
            nav = self._get("/x/web-interface/nav")
            if not nav.get("data", {}).get("isLogin"):
                raise BiliError(-101, "Cookie 无效或未登录", "auth")
            self._mid = nav["data"].get("mid")
            self._wbi = wbi.keys_from_nav(nav)
        return self._wbi

    # --- 业务接口 ---

    @property
    def self_mid(self) -> int:
        if self._mid is None:
            self._wbi_keys()
        assert self._mid is not None
        return self._mid

    def iter_followings(self, page_size: int = 50, max_pages: int | None = None) -> Iterator[dict[str, Any]]:
        """逐条产出关注列表。只读，不触发任何内容采集。"""
        pn = 1
        while True:
            data = self._get(
                "/x/relation/followings",
                {"vmid": self.self_mid, "pn": pn, "ps": page_size, "order": "desc", "order_type": "attention"},
            )["data"]
            rows = data.get("list") or []
            for row in rows:
                yield row
            total = data.get("total") or 0
            if not rows or pn * page_size >= total:
                return
            pn += 1
            if max_pages and pn > max_pages:
                return

    def list_videos(self, mid: int, page: int = 1, page_size: int = 30) -> list[dict[str, Any]]:
        """投稿元数据。只有标题/封面/时长/播放，不含视频内容。"""
        data = self._get(
            "/x/space/wbi/arc/search",
            {"mid": mid, "ps": page_size, "pn": page, "order": "pubdate", "platform": "web"},
            signed=True,
        )["data"]
        return (data.get("list") or {}).get("vlist") or []

    # --- 评论与动态 ---

    def top_comments(self, aid: int, limit: int = 20) -> list[dict[str, Any]]:
        """按热度取评论。只保留正文，作者信息由调用方丢弃。"""
        data = self._get(
            "/x/v2/reply",
            {"type": 1, "oid": aid, "sort": 2, "ps": max(1, min(limit, 20)), "pn": 1},
        )["data"]
        return (data or {}).get("replies") or []

    def iter_dynamics(self, mid: int, max_pages: int = 1) -> Iterator[dict[str, Any]]:
        """空间动态。返回原始 item，由上层做字段提取。"""
        offset = ""
        for _ in range(max_pages):
            self.rate.wait()
            params = {
                "host_mid": mid,
                "timezone_offset": -480,
                "features": "itemOpusStyle",
                "offset": offset or None,
            }
            params = {k: v for k, v in params.items() if v is not None}
            resp = self.http.get(
                "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space",
                params=params,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != 0:
                raise BiliError(payload.get("code", 0), payload.get("message", "动态接口错误"))
            data = payload.get("data") or {}
            items = data.get("items") or []
            for item in items:
                yield item
            offset = data.get("offset") or ""
            if not items or not offset or not data.get("has_more"):
                return
