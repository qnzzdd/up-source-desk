from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.repository import DemoRepository


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "demo.sqlite3", tmp_path / "no-dist")) as client:
        yield client


def test_account_and_status_are_explicit_demo(client):
    status = client.get("/api/status").json()
    assert status == {"mode": "demo", "backend": "ready", "storage": "sqlite", "live_available": False}
    account = client.get("/api/account").json()["account"]
    assert account["auth_state"] == "demo"
    assert account["following_count"] == 8
    assert account["group_count"] == 5


def test_group_memberships_and_empty_group(client):
    groups = client.get("/api/groups").json()["items"]
    for group in groups:
        data = client.get("/api/followings", params={"group_id": group["id"]}).json()
        assert data["pagination"]["total"] == group["member_count"]
        assert all(group["id"] in source["group_ids"] for source in data["items"])
    assert client.get("/api/followings?group_id=empty").json()["items"] == []


def test_pagination_and_search(client):
    first = client.get("/api/followings?limit=3").json()
    second = client.get("/api/followings?limit=3&offset=3").json()
    assert first["pagination"] == {"offset": 0, "limit": 3, "total": 8, "has_more": True}
    assert not ({s["uid"] for s in first["items"]} & {s["uid"] for s in second["items"]})
    assert len(client.get("/api/followings", params={"query": "像素"}).json()["items"]) == 1
    for query in ["' OR 1=1 --", "%", "_"]:
        assert client.get("/api/followings", params={"query": query}).json()["items"] == []
    assert client.get("/api/followings?offset=99").json()["pagination"]["has_more"] is False


@pytest.mark.parametrize("kind,expected", [("videos", 4), ("dynamics", 3)])
def test_content_pagination_and_empty(client, kind, expected):
    response = client.get(f"/api/sources/demo-01/{kind}?limit=2").json()
    assert response["pagination"]["total"] == expected
    assert response["pagination"]["has_more"]
    assert all(item["url"] is None for item in response["items"])
    assert client.get(f"/api/sources/demo-08/{kind}").json()["items"] == []


@pytest.mark.parametrize("suffix", ["", "/videos", "/dynamics"])
def test_missing_source(client, suffix):
    response = client.get("/api/sources/does-not-exist" + suffix)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SOURCE_NOT_FOUND"


@pytest.mark.parametrize("path", ["account", "groups", "followings", "sources/demo-01/videos", "status"])
def test_live_never_falls_back(client, path):
    response = client.get(f"/api/{path}?mode=live")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LIVE_NOT_CONNECTED"
    assert "items" not in response.json()


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "mode=other"])
def test_invalid_parameters(client, query):
    response = client.get("/api/followings?" + query)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PARAMETERS"


def test_no_writes_or_fallback_html(client):
    assert client.post("/api/sync").status_code == 404
    assert client.get("/api/not-found").json()["error"]["code"] == "API_NOT_FOUND"
    response = client.get("/api/account")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert client.get("/api/account", headers={"host": "evil.example"}).status_code == 400


def test_seed_is_idempotent(tmp_path):
    repo = DemoRepository(tmp_path / "seed.sqlite3")
    repo.initialize()
    repo.initialize()
    assert repo.followings(None, "", 0, 20)[1] == 8
    assert repo.contents("demo-01", "videos", 0, 20)[1] == 4


def test_future_schema_fails_clearly(tmp_path):
    repo = DemoRepository(tmp_path / "future.sqlite3")
    repo.initialize()
    with repo.connection() as con:
        con.execute("PRAGMA user_version=99")
    with pytest.raises(RuntimeError, match="Unsupported"):
        repo.initialize()
