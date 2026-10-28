"""Account-scoped metadata cache, deliberately separate from demo and credentials."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class LiveRepository:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        con = sqlite3.connect(self.path, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3):
                raise RuntimeError("Unsupported live database schema version")
            con.executescript("""
                CREATE TABLE IF NOT EXISTS live_sources (
                    account_uid TEXT NOT NULL, uid TEXT NOT NULL,
                    name TEXT NOT NULL, bio TEXT NOT NULL,
                    group_ids TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(account_uid, uid)
                );
                CREATE TABLE IF NOT EXISTS live_groups (
                    account_uid TEXT NOT NULL, id TEXT NOT NULL,
                    name TEXT NOT NULL, member_count INTEGER,
                    updated_at TEXT NOT NULL, PRIMARY KEY(account_uid, id)
                );
                CREATE TABLE IF NOT EXISTS live_cache_state (
                    account_uid TEXT PRIMARY KEY, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS live_accounts (
                    uid TEXT PRIMARY KEY, name TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS live_content (
                    account_uid TEXT NOT NULL, source_uid TEXT NOT NULL,
                    kind TEXT NOT NULL, id TEXT NOT NULL, text TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(account_uid, source_uid, kind, id)
                );
                CREATE TABLE IF NOT EXISTS live_content_state (
                    account_uid TEXT NOT NULL, source_uid TEXT NOT NULL,
                    kind TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(account_uid, source_uid, kind)
                );
                CREATE TABLE IF NOT EXISTS tool_groups (
                    account_uid TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL,
                    PRIMARY KEY(account_uid, id), UNIQUE(account_uid, name)
                );
                CREATE TABLE IF NOT EXISTS tool_members (
                    account_uid TEXT NOT NULL, group_id TEXT NOT NULL, source_uid TEXT NOT NULL,
                    PRIMARY KEY(account_uid, group_id, source_uid)
                );
                PRAGMA user_version=3;
            """)

    def save_account(self, account_uid, name):
        with self.connection() as con:
            con.execute("""INSERT INTO live_accounts VALUES (?, ?)
                ON CONFLICT(uid) DO UPDATE SET name=excluded.name""", (account_uid, name))

    def tool_groups(self, account_uid):
        with self.connection() as con:
            groups = con.execute("SELECT id, name FROM tool_groups WHERE account_uid=? ORDER BY name", (account_uid,)).fetchall()
            members = con.execute("SELECT group_id, source_uid FROM tool_members WHERE account_uid=?", (account_uid,)).fetchall()
            sources = con.execute("SELECT uid, name FROM live_sources WHERE account_uid=? ORDER BY name", (account_uid,)).fetchall()
        return {"items": [{**dict(g), "source_uids": [m["source_uid"] for m in members if m["group_id"] == g["id"]]} for g in groups],
                "sources": [dict(s) for s in sources]}

    def edit_tool_group(self, account_uid, action, group_id=None, name=None, source_uids=None):
        with self.connection() as con:
            if not con.execute("SELECT 1 FROM live_accounts WHERE uid=? UNION SELECT 1 FROM live_cache_state WHERE account_uid=?", (account_uid, account_uid)).fetchone():
                raise ValueError("本机没有该账号记录。")
            if action != "create" and not con.execute("SELECT 1 FROM tool_groups WHERE account_uid=? AND id=?", (account_uid, group_id)).fetchone():
                raise ValueError("本地分组不存在。")
            if action in ("create", "rename"):
                name = name.strip()
                if not name or len(name) > 60:
                    raise ValueError("分组名需为 1–60 个非空字符。")
                if con.execute("SELECT 1 FROM tool_groups WHERE account_uid=? AND name=? AND id!=?", (account_uid, name, group_id or "")).fetchone():
                    raise ValueError("该账号已有同名本地分组。")
                if action == "create":
                    con.execute("INSERT INTO tool_groups VALUES (?, ?, ?)", (account_uid, uuid.uuid4().hex, name))
                else:
                    con.execute("UPDATE tool_groups SET name=? WHERE account_uid=? AND id=?", (name, account_uid, group_id))
            elif action == "delete":
                con.execute("DELETE FROM tool_members WHERE account_uid=? AND group_id=?", (account_uid, group_id))
                con.execute("DELETE FROM tool_groups WHERE account_uid=? AND id=?", (account_uid, group_id))
            elif action == "members":
                ids = set(source_uids)
                saved = {r[0] for r in con.execute("SELECT uid FROM live_sources WHERE account_uid=?", (account_uid,))}
                if not ids <= saved:
                    raise ValueError("只能添加当前账号已保存的 UP。")
                con.execute("DELETE FROM tool_members WHERE account_uid=? AND group_id=?", (account_uid, group_id))
                con.executemany("INSERT INTO tool_members VALUES (?, ?, ?)", [(account_uid, group_id, uid) for uid in ids])
            else:
                raise ValueError("不支持的本地分组操作。")
        return self.tool_groups(account_uid)

    def accounts(self):
        with self.connection() as con:
            rows = con.execute("""SELECT ids.uid, COALESCE(a.name, ids.uid) AS name
                FROM (SELECT uid FROM live_accounts UNION SELECT account_uid FROM live_cache_state) ids
                LEFT JOIN live_accounts a ON a.uid=ids.uid ORDER BY ids.uid""").fetchall()
        return {"items": [dict(row) for row in rows]}

    def save_content(self, account_uid, source_uid, kind, items):
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as con:
            con.executemany("""INSERT INTO live_content VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_uid, source_uid, kind, id) DO UPDATE SET
                    text=excluded.text, updated_at=excluded.updated_at""",
                [(account_uid, source_uid, kind, item["id"], item["text"], now) for item in items])
            con.execute("""INSERT INTO live_content_state VALUES (?, ?, ?, ?)
                ON CONFLICT(account_uid, source_uid, kind) DO UPDATE SET updated_at=excluded.updated_at""",
                (account_uid, source_uid, kind, now))

    def load_content(self, account_uid, source_uid, kind):
        with self.connection() as con:
            rows = con.execute("""SELECT id, text FROM live_content
                WHERE account_uid=? AND source_uid=? AND kind=? ORDER BY updated_at DESC, id DESC""",
                (account_uid, source_uid, kind)).fetchall()
            state = con.execute("""SELECT updated_at FROM live_content_state
                WHERE account_uid=? AND source_uid=? AND kind=?""", (account_uid, source_uid, kind)).fetchone()
        return {"mode": "live", "items": [dict(row) for row in rows], "historical": True,
                "cached_at": state[0] if state else None, "scope": "saved_items"}

    def save_followings(self, account_uid, items):
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as con:
            con.executemany("""INSERT INTO live_sources VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_uid, uid) DO UPDATE SET
                    name=excluded.name, bio=excluded.bio,
                    group_ids=excluded.group_ids, updated_at=excluded.updated_at""",
                [(account_uid, item["uid"], item["name"], item["bio"],
                  json.dumps(item["group_ids"]), now) for item in items])
            self._touch(con, account_uid, now)

    def save_groups(self, account_uid, items):
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as con:
            con.executemany("""INSERT INTO live_groups VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account_uid, id) DO UPDATE SET
                    name=excluded.name, member_count=excluded.member_count,
                    updated_at=excluded.updated_at""",
                [(account_uid, item["id"], item["name"], item["member_count"], now)
                 for item in items])
            self._touch(con, account_uid, now)

    @staticmethod
    def _touch(con, account_uid, now):
        con.execute("""INSERT INTO live_cache_state VALUES (?, ?)
            ON CONFLICT(account_uid) DO UPDATE SET updated_at=excluded.updated_at""",
            (account_uid, now))

    def load(self, account_uid):
        with self.connection() as con:
            sources = con.execute("SELECT uid, name, bio, group_ids FROM live_sources WHERE account_uid=? ORDER BY uid", (account_uid,)).fetchall()
            groups = con.execute("SELECT id, name, member_count FROM live_groups WHERE account_uid=? ORDER BY id", (account_uid,)).fetchall()
            state = con.execute("SELECT updated_at FROM live_cache_state WHERE account_uid=?", (account_uid,)).fetchone()
        return {"mode": "live", "items": [{**dict(row), "group_ids": json.loads(row["group_ids"])} for row in sources],
                "groups": [dict(row) for row in groups], "cached_at": state[0] if state else None,
                "historical": True}
