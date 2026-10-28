import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.live import BilibiliReader
from backend.app.main import create_app


HEADERS = {"X-UPDesk-Local": "1"}


@pytest.fixture
def setup(tmp_path):
    calls = []
    responses = {}

    def handler(request):
        calls.append(request)
        return responses.get(request.url.path, httpx.Response(200, json={"code": -101}))

    reader = BilibiliReader(transport=httpx.MockTransport(handler), interval=0)
    with TestClient(create_app(tmp_path / "demo.db", tmp_path / "dist", reader)) as client:
        yield client, reader, responses, calls


def test_live_requires_local_header_and_origin(setup):
    client, _, _, calls = setup
    assert client.post('/api/live/qr').status_code == 403
    assert client.post('/api/live/qr', headers={**HEADERS, 'Origin': 'https://evil.invalid'}).status_code == 403
    assert not calls


def test_no_login_no_remote_follow_request(setup):
    client, _, _, calls = setup
    assert client.post('/api/live/followings', headers=HEADERS).status_code == 401
    assert not calls


def test_qr_unknown_state_never_authenticates(setup):
    client, reader, responses, _ = setup
    responses['/x/passport-login/web/qrcode/generate'] = httpx.Response(200, json={'code': 0, 'data': {
        'qrcode_key': 'secret-key', 'url': 'https://passport.bilibili.com/h5-app/passport/login/scan?key=test'}})
    result = client.post('/api/live/qr', headers=HEADERS)
    assert result.status_code == 200
    assert result.json()['image'].startswith('data:image/svg+xml;base64,')
    assert 'secret-key' not in result.text
    responses['/x/passport-login/web/qrcode/poll'] = httpx.Response(200, json={'code': 0, 'data': {'code': 999}})
    assert client.post('/api/live/poll', headers=HEADERS).status_code == 502
    assert reader.account is None


def test_authenticated_sample_and_disconnect(setup):
    client, reader, responses, calls = setup
    reader.account = {'uid': '1', 'name': 'test'}
    reader.cookie = 'SESSDATA=test-secret'
    responses['/x/relation/followings'] = httpx.Response(200, json={'code': 0, 'data': {
        'total': 3000, 'list': [{'mid': 2, 'uname': 'sample', 'tag': [5]}]}})
    result = client.post('/api/live/followings', headers=HEADERS)
    assert result.json()['partial'] is True
    assert result.json()['items'][0]['group_ids'] == [5]
    assert 'test-secret' not in result.text
    assert calls[-1].url.params['ps'] == '20'
    assert client.post('/api/live/sources/999/videos', headers=HEADERS).status_code == 400
    assert client.post('/api/live/disconnect', headers=HEADERS).status_code == 200
    assert reader.cookie is None and not reader.allowed


def test_risk_halts_subsequent_requests(setup):
    client, reader, responses, calls = setup
    reader.account = {'uid': '1'}
    reader.cookie = 'SESSDATA=test'
    responses['/x/relation/tags'] = httpx.Response(412)
    assert client.post('/api/live/groups', headers=HEADERS).status_code == 429
    assert client.post('/api/live/groups', headers=HEADERS).status_code == 429
    assert len(calls) == 1


def test_malformed_groups_not_empty_success(setup):
    client, reader, responses, _ = setup
    reader.account = {'uid': '1'}
    reader.cookie = 'SESSDATA=test'
    responses['/x/relation/tags'] = httpx.Response(200, json={'code': 0, 'data': {}})
    assert client.post('/api/live/groups', headers=HEADERS).status_code == 502


def test_login_success_requires_identity_and_hides_credentials(setup):
    import time
    client, reader, responses, _ = setup
    reader.key = 'test-key'
    reader.qr_started = time.monotonic()
    responses['/x/passport-login/web/qrcode/poll'] = httpx.Response(200, json={'code': 0, 'data': {
        'code': 0, 'url': 'https://passport.bilibili.com/callback?SESSDATA=private-value&bili_jct=private-jct&DedeUserID=12'}})
    responses['/x/web-interface/nav'] = httpx.Response(200, json={'code': 0, 'data': {'isLogin': True, 'mid': 12, 'uname': 'test'}})
    result = client.post('/api/live/poll', headers=HEADERS)
    assert result.json()['account']['uid'] == '12'
    assert 'private' not in result.text
    assert result.headers['cache-control'] == 'no-store'
    assert reader.key is None
