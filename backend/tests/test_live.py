import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.live import BilibiliReader, dynamic_text
from backend.app.main import create_app


HEADERS = {"X-UPDesk-Local": "1"}


@pytest.mark.parametrize("dynamic, expected", [
    ({"desc": {"text": "普通文字"}}, "普通文字"),
    ({"major": {"opus": {"title": "图文标题", "summary": {"text": "图片配文"}, "pics": [{"url": "https://invalid"}]}}}, "图文标题\n图片配文"),
    ({"desc": {"text": "分享说明"}, "major": {"archive": {"title": "视频标题", "desc": "视频简介"}}}, "分享说明\n视频标题\n视频简介"),
    ({"major": {"article": {"title": "专栏标题", "desc": "专栏摘要"}}}, "专栏标题\n专栏摘要"),
    ({"major": {"draw": {"items": [{"src": "https://invalid"}]}}}, ""),
    ({"desc": {"text": "相同"}, "major": {"opus": {"summary": {"text": "相同"}}}}, "相同"),
    ({"major": {"common": {"title": {"unexpected": "不序列化"}, "desc": "有效文字"}}}, "有效文字"),
])
def test_dynamic_text_known_fields(dynamic, expected):
    assert dynamic_text({"modules": {"module_dynamic": dynamic}}) == expected


def test_forwarded_dynamic_preserves_original_text():
    item = {"modules": {"module_dynamic": {"desc": {"text": "我的评论"}}},
            "orig": {"modules": {"module_dynamic": {"major": {"opus": {"summary": {"text": "原图文"}}}}}}}
    assert dynamic_text(item) == "我的评论\n转发原文：\n原图文"


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


def test_login_accepts_set_cookie_without_callback_credentials(setup):
    import time
    client, reader, responses, calls = setup
    reader.key = 'test-key'
    reader.qr_started = time.monotonic()
    responses['/x/passport-login/web/qrcode/poll'] = httpx.Response(200,
        headers=[('set-cookie', 'SESSDATA=private%2Cvalue; Domain=.bilibili.com; Path=/; Secure; HttpOnly'),
                 ('set-cookie', 'DedeUserID=12; Domain=.bilibili.com; Path=/; Secure')],
        json={'code': 0, 'data': {'code': 0, 'url': 'https://www.bilibili.com/'}})
    responses['/x/web-interface/nav'] = httpx.Response(200, json={'code': 0,
        'data': {'isLogin': True, 'mid': 12, 'uname': 'test'}})
    result = client.post('/api/live/poll', headers=HEADERS)
    assert result.status_code == 200
    assert result.json()['state'] == 'connected'
    assert 'private' not in result.text
    assert 'SESSDATA=private%2Cvalue' in calls[-1].headers['cookie']


def test_stale_cookie_jar_cannot_complete_new_login(setup):
    import time
    client, reader, responses, _ = setup
    reader.key = 'test-key'
    reader.qr_started = time.monotonic()
    reader.http.cookies.set('SESSDATA', 'old-secret', domain='.bilibili.com')
    responses['/x/passport-login/web/qrcode/poll'] = httpx.Response(200,
        json={'code': 0, 'data': {'code': 0, 'url': 'https://www.bilibili.com/'}})
    result = client.post('/api/live/poll', headers=HEADERS)
    assert result.status_code == 502
    assert reader.account is None


def test_manual_following_pages_keep_previous_sources_and_deduplicate(setup):
    client, reader, responses, calls = setup
    reader.account = {'uid': '1'}
    reader.cookie = 'SESSDATA=test'
    path = '/x/relation/followings'
    def respond(rows, total=3):
        responses[path] = httpx.Response(200, json={'code': 0, 'data': {'total': total, 'list': rows}})
    assert client.post('/api/live/followings-next', headers=HEADERS).status_code == 409
    assert not calls
    respond([{'mid': 2}, {'mid': 3}])
    assert client.post('/api/live/followings', headers=HEADERS).json()['has_more']
    respond([{'mid': 3}, {'mid': 4}])
    result = client.post('/api/live/followings-next', headers=HEADERS).json()
    assert result['loaded'] == 3 and not result['has_more']
    assert reader.allowed == {'2', '3', '4'}
    assert calls[-1].url.params['pn'] == '2'
    respond([{'mid': 5}])
    client.post('/api/live/followings', headers=HEADERS)
    assert reader.allowed == {'5'} and reader.follow_page == 1


def test_failed_page_can_be_retried_and_empty_page_stays_partial(setup):
    client, reader, responses, calls = setup
    reader.account = {'uid': '1'}
    reader.cookie = 'SESSDATA=test'
    path = '/x/relation/followings'
    responses[path] = httpx.Response(200, json={'code': 0, 'data': {'total': 30, 'list': [{'mid': 2}]}})
    client.post('/api/live/followings', headers=HEADERS)
    responses[path] = httpx.Response(500)
    assert client.post('/api/live/followings-next', headers=HEADERS).status_code == 502
    assert reader.follow_page == 1 and reader.allowed == {'2'}
    responses[path] = httpx.Response(200, json={'code': 0, 'data': {'total': 30, 'list': []}})
    result = client.post('/api/live/followings-next', headers=HEADERS).json()
    assert calls[-1].url.params['pn'] == '2'
    assert result['partial'] and not result['has_more'] and result['warning']
