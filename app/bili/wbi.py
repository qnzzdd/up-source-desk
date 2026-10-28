"""B 站 wbi 签名。参考公开实现，无第三方依赖。"""
from __future__ import annotations

import hashlib
import time
import urllib.parse

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def _key_from_url(url: str) -> str:
    return url.rsplit("/", 1)[-1].split(".", 1)[0]


def get_mixin_key(img_key: str, sub_key: str) -> str:
    raw = img_key + sub_key
    return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def sign(params: dict, img_key: str, sub_key: str, now: int | None = None) -> dict:
    mixin_key = get_mixin_key(img_key, sub_key)
    signed = dict(params)
    signed["wts"] = int(now if now is not None else time.time())
    signed = {
        k: "".join(ch for ch in str(v) if ch not in "!'()*")
        for k, v in sorted(signed.items())
    }
    query = urllib.parse.urlencode(signed)
    signed["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return signed


def keys_from_nav(nav_json: dict) -> tuple[str, str]:
    wbi = nav_json["data"]["wbi_img"]
    return _key_from_url(wbi["img_url"]), _key_from_url(wbi["sub_url"])
