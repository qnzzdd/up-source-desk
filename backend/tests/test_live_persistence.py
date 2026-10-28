import httpx
from fastapi.testclient import TestClient

from backend.app.live import BilibiliReader
from backend.app.main import create_app


HEADERS = {"X-UPDesk-Local": "1"}


def build(tmp_path, responses, uid="1"):
    def handler(request):
        return responses.get(request.url.path, httpx.Response(500))
    reader = BilibiliReader(transport=httpx.MockTransport(handler), interval=0)
    reader.account = {"uid": uid, "name": "test"}
    reader.cookie = "SESSDATA=credential-never-store"
    reader.key = "qr-secret-never-store"
    app = create_app(tmp_path / "demo.db", tmp_path / "dist", reader)
    return TestClient(app), reader


def sources(rows, total=20):
    return httpx.Response(200, json={"code": 0, "data": {"total": total, "list": rows}})


def test_restart_loads_account_scoped_historical_cache(tmp_path):
    responses = {
        "/x/relation/followings": sources([{"mid": 2, "uname": "saved", "sign": "bio", "tag": [5], "private": "raw-response-secret"}]),
        "/x/relation/tags": httpx.Response(200, json={"code": 0, "data": [{"tagid": 5, "name": "group", "count": 1}]}),
    }
    client, _ = build(tmp_path, responses)
    with client:
        assert client.post("/api/live/followings", headers=HEADERS).status_code == 200
        assert client.post("/api/live/groups", headers=HEADERS).status_code == 200
    client, reader = build(tmp_path, {})
    with client:
        reader.follow_page = 12
        reader.follow_has_more = True
        result = client.post("/api/live/cache", headers=HEADERS).json()
        assert result["items"] == [{"uid": "2", "name": "saved", "bio": "bio", "group_ids": [5]}]
        assert result["groups"] == [{"id": "5", "name": "group", "member_count": 1}]
        assert result["historical"] and result["cached_at"]
        assert reader.allowed == {"2"}
        assert reader.follow_page == 0 and not reader.follow_has_more
        assert client.post("/api/live/followings-next", headers=HEADERS).status_code == 409
        assert client.post("/api/live/cache").status_code == 403
        client.post("/api/live/disconnect", headers=HEADERS)
        assert client.post("/api/live/cache", headers=HEADERS).status_code == 401
    client, reader = build(tmp_path, {}, uid="99")
    with client:
        result = client.post("/api/live/cache", headers=HEADERS).json()
        assert result["items"] == result["groups"] == []
        assert result["cached_at"] is None and not reader.allowed
    contents = (tmp_path / "live.sqlite3").read_bytes()
    for secret in (b"credential-never-store", b"qr-secret-never-store", b"raw-response-secret", b"SESSDATA"):
        assert secret not in contents


def test_partial_refresh_and_failure_preserve_history(tmp_path):
    responses = {"/x/relation/followings": sources([{"mid": 2}, {"mid": 3}])}
    client, reader = build(tmp_path, responses)
    with client:
        client.post("/api/live/followings", headers=HEADERS)
        responses["/x/relation/followings"] = sources([{"mid": 2, "uname": "renamed"}])
        client.post("/api/live/followings", headers=HEADERS)
        before = client.post("/api/live/cache", headers=HEADERS).json()
        assert {item["uid"] for item in before["items"]} == {"2", "3"}
        assert before["items"][0]["name"] == "renamed"
        responses["/x/relation/followings"] = httpx.Response(500)
        assert client.post("/api/live/followings", headers=HEADERS).status_code == 502
        assert client.post("/api/live/cache", headers=HEADERS).json() == before
        responses["/x/relation/followings"] = sources([{"mid": 4}, {"bad": "row"}])
        assert client.post("/api/live/followings", headers=HEADERS).status_code == 502
        assert client.post("/api/live/cache", headers=HEADERS).json() == before


def test_disk_failure_does_not_advance_page(tmp_path, monkeypatch):
    import sqlite3
    client, reader = build(tmp_path, {"/x/relation/followings": sources([{"mid": 2}])})
    with client:
        def fail(*args):
            raise sqlite3.OperationalError("sensitive path")
        monkeypatch.setattr(reader.repository, "save_followings", fail)
        response = client.post("/api/live/followings", headers=HEADERS)
        assert response.status_code == 503
        assert "sensitive path" not in response.text
        assert reader.follow_page == 0 and not reader.allowed


def test_offline_restart_restores_metadata_and_content_without_platform_calls(tmp_path):
    responses = {
        '/x/relation/followings': sources([{'mid': 2, 'uname': 'saved', 'tag': [5]}]),
        '/x/relation/tags': httpx.Response(200, json={'code': 0, 'data': [{'tagid': 5, 'name': 'group'}]}),
        '/x/web-interface/nav': httpx.Response(200, json={'code': 0, 'data': {'isLogin': True, 'mid': 1, 'uname': 'owner', 'wbi_img': {
            'img_url': 'https://example.invalid/' + 'a' * 32 + '.png', 'sub_url': 'https://example.invalid/' + 'b' * 32 + '.png'}}}),
        '/x/space/wbi/arc/search': httpx.Response(200, json={'code': 0, 'data': {'list': {'vlist': [{'bvid': 'BVtest', 'title': 'saved video'}]}}}),
        '/x/polymer/web-dynamic/v1/feed/space': httpx.Response(200, json={'code': 0, 'data': {'items': [{'id_str': '123', 'modules': {'module_dynamic': {'desc': {'text': 'saved text'}}}}]}}),
    }
    client, reader = build(tmp_path, responses)
    with client:
        assert client.post('/api/live/account', headers=HEADERS).status_code == 200
        assert client.post('/api/live/followings', headers=HEADERS).status_code == 200
        assert client.post('/api/live/groups', headers=HEADERS).status_code == 200
        for kind in ('videos', 'dynamics'):
            assert client.post(f'/api/live/sources/2/{kind}', headers=HEADERS).status_code == 200
        responses['/x/space/wbi/arc/search'] = httpx.Response(500)
        assert client.post('/api/live/sources/2/videos', headers=HEADERS).status_code == 502
    def reject_remote(request):
        raise AssertionError('Offline browsing must not request Bilibili')
    reader = BilibiliReader(transport=httpx.MockTransport(reject_remote), interval=0)
    with TestClient(create_app(tmp_path / 'demo.db', tmp_path / 'dist', reader)) as client:
        assert client.post('/api/live/session', headers=HEADERS).json() == {'account': None}
        assert client.post('/api/live/local-accounts', headers=HEADERS).json() == {'items': [{'uid': '1', 'name': 'owner'}]}
        cached = client.post('/api/live/local/1', headers=HEADERS).json()
        assert cached['items'][0]['uid'] == '2' and cached['groups'][0]['id'] == '5'
        for kind, expected in [('videos', 'saved video'), ('dynamics', 'saved text')]:
            result = client.post(f'/api/live/local/1/sources/2/{kind}', headers=HEADERS).json()
            assert result['items'][0]['text'] == expected and result['cached_at']
            assert result['historical'] and result['scope'] == 'saved_items'
            assert client.post(f'/api/live/local/99/sources/2/{kind}', headers=HEADERS).json()['items'] == []
        assert client.post('/api/live/local/99', headers=HEADERS).json()['items'] == []
        assert not reader.allowed and reader.follow_page == 0 and not reader.cookie
        assert client.post('/api/live/local/1/sources/2/unknown', headers=HEADERS).status_code == 404
        for path in ('session', 'local-accounts', 'local/1', 'local/1/sources/2/videos'):
            assert client.post('/api/live/' + path).status_code == 403
            assert client.post('/api/live/' + path, headers={**HEADERS, 'Origin': 'https://evil.invalid'}).status_code == 403


def test_v1_database_migrates_without_losing_history(tmp_path):
    import sqlite3
    path = tmp_path / 'live.sqlite3'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE live_cache_state (account_uid TEXT PRIMARY KEY, updated_at TEXT NOT NULL)')
        con.execute("INSERT INTO live_cache_state VALUES ('old-owner', '2026-01-01')")
        con.execute('PRAGMA user_version=1')
    client, _ = build(tmp_path, {})
    with client:
        result = client.post('/api/live/local-accounts', headers=HEADERS).json()
        assert result == {'items': [{'uid': 'old-owner', 'name': 'old-owner'}]}
        assert client.post('/api/live/local/old-owner', headers=HEADERS).json()['cached_at'] == '2026-01-01'
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 4
