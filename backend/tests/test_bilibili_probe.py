"""Offline tests of diagnostic safety, not evidence of live platform access."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest


spec = importlib.util.spec_from_file_location(
    "bilibili_probe", Path(__file__).resolve().parents[2] / "scripts/check_bilibili_api.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize("status,body,expected", [
    (200, {"code": -101}, "authentication_required"),
    (200, {"code": -352}, "risk_control_stop"),
    (412, {"code": 0}, "risk_control_stop"),
    (429, {"code": 0}, "risk_control_stop"),
    (503, {"code": 0}, "http_error"),
    (200, {"code": 0}, "anonymous_api_success_not_live_acceptance"),
    (200, {"code": False}, "api_error_or_unexpected_response"),
])
def test_response_classification(status, body, expected):
    assert probe.summarize(httpx.Response(status, json=body))["outcome"] == expected


def test_unsigned_response_is_not_feature_acceptance():
    result = probe.summarize(httpx.Response(200, json={"code": 0}), signed_required=True)
    assert result["outcome"] == "unsigned_reachability_only"


def test_risk_stops_other_api_requests():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(412, text="blocked")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        results = probe.probe(client, include_qr=False, interval=0)
    assert len(calls) == 1
    assert all(r["outcome"] == "skipped_after_risk_control" for r in results[1:])


def test_qr_keys_and_cookies_never_appear_in_report():
    secret = "test-secret-not-for-output"

    def handler(request):
        if request.url.path.endswith("generate"):
            return httpx.Response(200, json={"code": 0, "data": {
                "url": "https://example.invalid/" + secret, "qrcode_key": secret}},
                headers={"set-cookie": "test_cookie=" + secret})
        if request.url.path.endswith("poll"):
            assert request.url.params["qrcode_key"] == secret
            return httpx.Response(200, json={"code": 0, "data": {"code": 86101}})
        return httpx.Response(200, json={"code": -101})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        results = probe.probe(client, include_qr=True, interval=0)
    assert results[-1]["outcome"] == "waiting_for_scan_verified"
    assert secret not in json.dumps(results)


def test_transport_error_does_not_expose_url():
    def handler(request):
        raise httpx.ConnectError("secret-url", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        results = probe.probe(client, include_qr=False, interval=0)
    assert results[0]["error_type"] == "ConnectError"
    assert "secret-url" not in json.dumps(results)
