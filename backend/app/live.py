"""Single-user, memory-only Bilibili reader. No automatic crawling or retries."""
import asyncio
import base64
import io
import ssl
import time
from urllib.parse import parse_qs, urlparse

import httpx
import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, Request

from app.bili.wbi import keys_from_nav, sign


class LiveError(Exception):
    def __init__(self, code, message, status=502):
        self.code, self.message, self.status = code, message, status


class BilibiliReader:
    def __init__(self, transport=None, interval=3):
        self.http = httpx.AsyncClient(transport=transport, verify=ssl.create_default_context(),
            trust_env=False, timeout=20, follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"})
        self.lock = asyncio.Lock()
        self.interval = interval
        self.last = 0.0
        self.blocked_until = 0.0
        self.key = None
        self.qr_started = 0.0
        self.account = None
        self.cookie = None
        self.allowed = set()

    async def request(self, path, params=None, passport=False):
        now = time.monotonic()
        if now < self.blocked_until:
            raise LiveError("RISK_COOLDOWN", "平台触发风控，已暂停请求十分钟。", 429)
        await asyncio.sleep(max(0, self.interval - (now - self.last)))
        self.last = time.monotonic()
        base = "https://passport.bilibili.com" if passport else "https://api.bilibili.com"
        headers = {"Cookie": self.cookie} if self.cookie and not passport else {}
        try:
            response = await self.http.get(base + path, params=params, headers=headers)
            if response.status_code in (412, 429):
                self.blocked_until = time.monotonic() + 600
                raise LiveError("RISK_COOLDOWN", "平台拒绝请求，已暂停十分钟；未自动重试。", 429)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError):
            raise LiveError("UPSTREAM_UNAVAILABLE", "平台网络或响应异常，请稍后手动重试。") from None
        if not isinstance(body, dict) or type(body.get("code")) is not int:
            raise LiveError("SCHEMA_CHANGED", "平台响应结构异常，未视为无数据。")
        if body["code"] in (-352, -412):
            self.blocked_until = time.monotonic() + 600
            raise LiveError("RISK_COOLDOWN", "平台风控，已暂停十分钟。", 429)
        if body["code"] == -101:
            self.account = None
            self.cookie = None
            self.allowed.clear()
            self.http.cookies.clear()
            raise LiveError("LOGIN_REQUIRED", "请扫码登录或重新验证账号。", 401)
        if body["code"] != 0:
            raise LiveError("UPSTREAM_REJECTED", f"平台业务错误：{body['code']}。")
        if "data" not in body:
            raise LiveError("SCHEMA_CHANGED", "平台未返回 data 字段。")
        return body["data"]

    async def identity(self):
        data = await self.request("/x/web-interface/nav")
        if not isinstance(data, dict) or not data.get("isLogin") or not data.get("mid"):
            raise LiveError("LOGIN_REQUIRED", "尚未获得有效账号身份。", 401)
        self.account = {"uid": str(data["mid"]), "name": str(data.get("uname", ""))}
        return self.account

    async def generate(self):
        if self.account:
            raise LiveError("ALREADY_CONNECTED", "请先断开当前账号，再切换账号。", 409)
        if self.key and time.monotonic() - self.qr_started < 10:
            raise LiveError("QR_TOO_FREQUENT", "请稍后再刷新二维码。", 429)
        data = await self.request("/x/passport-login/web/qrcode/generate", passport=True)
        if not isinstance(data, dict) or not isinstance(data.get("qrcode_key"), str):
            raise LiveError("SCHEMA_CHANGED", "二维码响应无效。")
        url = data.get("url", "")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"passport.bilibili.com", "account.bilibili.com"}:
            raise LiveError("SCHEMA_CHANGED", "二维码地址不属于 B站登录服务。")
        self.key, self.qr_started = data["qrcode_key"], time.monotonic()
        image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
        out = io.BytesIO()
        image.save(out)
        return {"state": "waiting_scan", "image": "data:image/svg+xml;base64," + base64.b64encode(out.getvalue()).decode()}

    async def poll(self):
        if not self.key or time.monotonic() - self.qr_started > 180:
            self.key = None
            return {"state": "expired"}
        data = await self.request("/x/passport-login/web/qrcode/poll", {"qrcode_key": self.key}, passport=True)
        if not isinstance(data, dict):
            raise LiveError("SCHEMA_CHANGED", "扫码状态响应无效。")
        code = data.get("code")
        states = {86101: "waiting_scan", 86090: "waiting_confirm", 86038: "expired"}
        if code in states:
            if code == 86038:
                self.key = None
            return {"state": states[code]}
        if type(code) is not int or code != 0:
            raise LiveError("QR_UNKNOWN_STATE", "未知扫码状态，未判定登录成功。")
        values = parse_qs(urlparse(data.get("url", "")).query)
        cookies = {k: values.get(k, [""])[0] for k in ("SESSDATA", "bili_jct", "DedeUserID")}
        if not cookies["SESSDATA"] or any(any(c in v for c in "\r\n;") for v in cookies.values()):
            raise LiveError("SCHEMA_CHANGED", "未收到安全有效的登录凭据。")
        self.cookie = "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
        self.key = None
        return {"state": "connected", "account": await self.identity()}

    def require_account(self):
        if not self.account or not self.cookie:
            raise LiveError("LOGIN_REQUIRED", "先扫码并验证账号身份。", 401)

    async def followings(self):
        self.require_account()
        data = await self.request("/x/relation/followings", {"vmid": self.account["uid"], "pn": 1, "ps": 20, "order": "desc", "order_type": ""})
        if not isinstance(data, dict) or not isinstance(data.get("list"), list) or type(data.get("total")) is not int:
            raise LiveError("SCHEMA_CHANGED", "关注列表结构异常，未更新数据。")
        items = []
        for row in data["list"]:
            if not isinstance(row, dict) or not row.get("mid"):
                raise LiveError("SCHEMA_CHANGED", "关注条目缺少账号 ID。")
            items.append({"uid": str(row["mid"]), "name": str(row.get("uname", "")),
                          "bio": str(row.get("sign", "")), "group_ids": row.get("tag")})
        self.allowed = {row["uid"] for row in items}
        return {"mode": "live", "items": items, "total": data["total"],
                "partial": len(items) < data["total"], "scope": "first_20_only"}

    async def groups(self):
        self.require_account()
        data = await self.request("/x/relation/tags")
        if not isinstance(data, list) or any(not isinstance(g, dict) or "tagid" not in g for g in data):
            raise LiveError("SCHEMA_CHANGED", "分组响应异常，不视为未分组。")
        return {"mode": "live", "items": [{"id": str(g["tagid"]), "name": str(g.get("name", "")),
                "member_count": g.get("count")} for g in data]}

    async def content(self, uid, kind):
        self.require_account()
        if uid not in self.allowed:
            raise LiveError("SOURCE_NOT_LOADED", "请先读取关注样本并从列表中选择 UP。", 400)
        nav = await self.request("/x/web-interface/nav")
        try:
            keys = keys_from_nav({"data": nav})
            params = {"mid": uid, "pn": 1, "ps": 20, "order": "pubdate", "platform": "web"} if kind == "videos" else {"host_mid": uid, "offset": "", "timezone_offset": -480, "features": "itemOpusStyle"}
            params = sign(params, *keys)
        except (KeyError, TypeError, IndexError):
            raise LiveError("SIGNING_UNAVAILABLE", "平台签名参数不可用。") from None
        path = "/x/space/wbi/arc/search" if kind == "videos" else "/x/polymer/web-dynamic/v1/feed/space"
        data = await self.request(path, params)
        try:
            rows = data["list"]["vlist"] if kind == "videos" else data["items"]
            if not isinstance(rows, list):
                raise TypeError()
            items = [{"id": str(r["bvid"]), "text": str(r["title"])} for r in rows] if kind == "videos" else [
                {"id": str(r["id_str"]), "text": str((r["modules"].get("module_dynamic", {}).get("desc") or {}).get("text") or "非纯文字动态，请到 B站查看原内容")} for r in rows]
        except (KeyError, TypeError, AttributeError):
            raise LiveError("SCHEMA_CHANGED", "内容响应结构异常，未视为无更新。") from None
        return {"mode": "live", "items": items, "scope": "first_page_only"}


def router(reader):
    async def guard(request: Request):
        if request.headers.get("X-UPDesk-Local") != "1" or request.headers.get("sec-fetch-site") == "cross-site":
            raise LiveError("LOCAL_REQUEST_REQUIRED", "仅允许本机页面操作。", 403)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise LiveError("ORIGIN_REJECTED", "拒绝跨来源请求。", 403)

    api = APIRouter(prefix="/api/live", dependencies=[Depends(guard)])

    @api.post("/{action}")
    async def action(action: str):
        async with reader.lock:
            if action == "qr":
                return await reader.generate()
            if action == "poll":
                return await reader.poll()
            if action == "account":
                reader.require_account()
                return {"account": await reader.identity()}
            if action == "followings":
                return await reader.followings()
            if action == "groups":
                return await reader.groups()
            if action == "disconnect":
                reader.cookie = reader.account = reader.key = None
                reader.allowed.clear()
                reader.http.cookies.clear()
                return {"state": "disconnected"}
            raise LiveError("NOT_FOUND", "操作不存在。", 404)

    @api.post("/sources/{uid}/{kind}")
    async def content(uid: str, kind: str):
        if kind not in ("videos", "dynamics"):
            raise LiveError("NOT_FOUND", "内容类型不存在。", 404)
        async with reader.lock:
            return await reader.content(uid, kind)

    return api
