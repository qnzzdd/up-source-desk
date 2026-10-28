import httpx
from fastapi.testclient import TestClient

from backend.app.live import BilibiliReader
from backend.app.main import create_app

HEADERS = {"X-UPDesk-Local": "1"}
BASE = "/api/live/local/1/tool-groups"


def make_client(tmp_path):
    def reject(request):
        raise AssertionError("Local grouping must not request Bilibili")
    reader = BilibiliReader(transport=httpx.MockTransport(reject))
    return TestClient(create_app(tmp_path / "demo.db", tmp_path / "dist", reader)), reader


def test_group_crud_membership_restart_and_isolation(tmp_path):
    client, reader = make_client(tmp_path)
    with client:
        reader.repository.save_account("1", "owner")
        reader.repository.save_followings("1", [{"uid": "2", "name": "source", "bio": "", "group_ids": [5]}])
        reader.repository.save_groups("1", [{"id": "5", "name": "platform", "member_count": 1}])
        post = lambda path, body: client.post(path, headers=HEADERS, json=body)
        assert client.post(BASE).status_code == 403
        assert post(BASE + "/create", {"name": "  "}).status_code == 400
        result = post(BASE + "/create", {"name": "Local"})
        assert result.status_code == 200
        gid = result.json()["items"][0]["id"]
        assert post(BASE + "/create", {"name": "Local"}).status_code == 400
        assert post(f"{BASE}/{gid}/members", {"source_uids": ["2", "2"]}).json()["items"][0]["source_uids"] == ["2"]
        assert post(f"{BASE}/{gid}/members", {"source_uids": ["999"]}).status_code == 400
        assert post(f"{BASE}/{gid}/rename", {"name": "Renamed"}).status_code == 200
        assert client.post("/api/live/local/99/tool-groups", headers=HEADERS).json()["items"] == []
        assert post(f"/api/live/local/99/tool-groups/{gid}/delete", {}).status_code == 400
    client, reader = make_client(tmp_path)
    with client:
        saved = client.post(BASE, headers=HEADERS).json()["items"][0]
        assert saved == {"id": gid, "name": "Renamed", "source_uids": ["2"]}
        assert client.post(f"{BASE}/{gid}/delete", headers=HEADERS, json={}).json()["items"] == []
        platform = reader.repository.load("1")
        assert platform["groups"][0]["name"] == "platform"
        assert platform["items"][0]["uid"] == "2"
