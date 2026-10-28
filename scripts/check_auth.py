"""只读鉴权自检：不采集任何内容，只确认 Cookie 有效并给出账号概况。

用法:
    python3 -m scripts.check_auth
"""
from __future__ import annotations

from app.bili.client import BiliClient, BiliError
from app.config import load_settings


def mask(raw: str) -> str:
    """打印时遮蔽 Cookie 值，避免日志泄露。"""
    out = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        key, _, val = part.partition("=")
        out.append(f"{key}=***({len(val)}字符)")
    return "; ".join(out)


def main() -> int:
    s = load_settings()
    if not s.has_cookie:
        print("未找到 Cookie。请把 cookie.txt 放在项目根目录，内容形如：")
        print("SESSDATA=...; bili_jct=...")
        return 1

    print(f"读取到 Cookie: {mask(s.cookie)}")
    try:
        with BiliClient(s) as client:
            nav = client._get("/x/web-interface/nav")["data"]
            print(f"登录状态 : {'已登录' if nav.get('isLogin') else '未登录'}")
            print(f"账号     : {nav.get('uname')}  (mid={nav.get('mid')})")
            print(f"等级     : Lv{nav.get('level')}   大会员: {nav.get('vipStatus')}")
            print(f"硬币     : {nav.get('money')}")

            rel = client._get(
                "/x/relation/stat", {"vmid": client.self_mid}
            )["data"]
            print(f"关注     : {rel.get('following')}   粉丝: {rel.get('follower')}")

            first = next(client.iter_followings(page_size=50), None)
            if first:
                print(f"首个关注 : {first.get('uname')} (mid={first.get('mid')})")
            print("接口可用：关注列表可读取")
    except BiliError as exc:
        print(f"失败：{exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
