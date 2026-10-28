"""Bounded anonymous diagnostics, not an authenticated integration test."""

from __future__ import annotations

import argparse
import json
import ssl
import time
from datetime import datetime, timedelta, timezone

import httpx


RISK_CODES = {-352, -412}
HEADERS = {
    "User-Agent": "Mozilla/5.0 UPSourceDesk/0.1 (read-only compatibility probe)",
    "Referer": "https://www.bilibili.com/",
}


def summarize(response: httpx.Response, *, signed_required: bool = False) -> dict:
    """Allowlist output; never serialize bodies, cookies, URLs or login keys."""
    result = {"http_status": response.status_code, "api_code": None}
    try:
        body = response.json()
    except ValueError:
        body = None
    code = body.get("code") if isinstance(body, dict) else None
    if isinstance(code, int) and not isinstance(code, bool):
        result["api_code"] = code
    if response.status_code in (412, 429) or result["api_code"] in RISK_CODES:
        result["outcome"] = "risk_control_stop"
    elif response.status_code != 200:
        result["outcome"] = "http_error"
    elif result["api_code"] == -101:
        result["outcome"] = "authentication_required"
    elif signed_required:
        result["outcome"] = "unsigned_reachability_only"
    elif result["api_code"] == 0:
        result["outcome"] = "anonymous_api_success_not_live_acceptance"
    else:
        result["outcome"] = "api_error_or_unexpected_response"
    return result


def request_summary(client: httpx.Client, name: str, url: str, **kwargs) -> dict:
    signed_required = kwargs.pop("signed_required", False)
    try:
        response = client.get(url, **kwargs)
        return {"name": name, **summarize(response, signed_required=signed_required)}
    except httpx.HTTPError as exc:
        # Exception messages can contain request URLs. Record only their type.
        return {"name": name, "outcome": "transport_error", "error_type": type(exc).__name__}


def probe(client: httpx.Client, *, include_qr: bool, interval: float = 3.0) -> list[dict]:
    api = "https://api.bilibili.com"
    targets = [
        ("account_nav", "/x/web-interface/nav", {}, False),
        ("following_first_page", "/x/relation/followings", {"vmid": 2, "pn": 1, "ps": 1}, False),
        ("own_groups", "/x/relation/tags", {}, False),
        ("up_videos_unsigned", "/x/space/wbi/arc/search", {"mid": 2, "pn": 1, "ps": 1}, True),
        ("up_dynamics_unsigned", "/x/polymer/web-dynamic/v1/feed/space", {"host_mid": 2}, True),
    ]
    results = []
    stopped = False
    for name, path, params, signed in targets:
        if stopped:
            results.append({"name": name, "outcome": "skipped_after_risk_control"})
            continue
        if results:
            time.sleep(interval)
        result = request_summary(client, name, api + path, params=params, signed_required=signed)
        results.append(result)
        stopped = result["outcome"] in {"risk_control_stop", "transport_error"}

    if include_qr:
        time.sleep(interval)
        base = "https://passport.bilibili.com/x/passport-login/web/qrcode/"
        try:
            response = client.get(base + "generate", params={"source": "main-fe-header"})
            result = {"name": "qr_generate", **summarize(response)}
            results.append(result)
            if result["api_code"] == 0 and response.status_code == 200:
                data = response.json().get("data")
                key = data.get("qrcode_key") if isinstance(data, dict) else None
                url = data.get("url") if isinstance(data, dict) else None
                if not isinstance(key, str) or not key or not isinstance(url, str) or not url:
                    result["outcome"] = "invalid_qr_schema"
                else:
                    result["outcome"] = "qr_schema_verified_no_login"
                    time.sleep(interval)
                    poll = client.get(base + "poll", params={"qrcode_key": key, "source": "main-fe-header"})
                    poll_result = {"name": "qr_poll_once", **summarize(poll)}
                    if poll_result["api_code"] == 0 and poll.status_code == 200:
                        state = poll.json().get("data", {}).get("code")
                        if isinstance(state, int) and not isinstance(state, bool):
                            poll_result["login_state_code"] = state
                        poll_result["outcome"] = "waiting_for_scan_verified" if state == 86101 else "unexpected_login_state"
                    results.append(poll_result)
        except httpx.HTTPError as exc:
            results.append({"name": "qr_transport", "outcome": "transport_error", "error_type": type(exc).__name__})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-network", action="store_true", help="Explicitly allow at most five API GETs.")
    parser.add_argument("--include-qr", action="store_true", help="Also generate one ephemeral QR challenge and poll once; never log in.")
    args = parser.parse_args()
    if not args.allow_network:
        parser.error("Network is opt-in: pass --allow-network")
    # Use OS trust roots without disabling TLS verification; ignore proxy env vars.
    with httpx.Client(verify=ssl.create_default_context(), timeout=20, headers=HEADERS,
                      follow_redirects=False, trust_env=False) as client:
        results = probe(client, include_qr=args.include_qr)
    print(json.dumps({"checked_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                      "authenticated": False, "results": results}, indent=2))


if __name__ == "__main__":
    main()
