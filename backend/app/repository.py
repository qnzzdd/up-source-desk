"""Local demo persistence. Remote-provider logic must not enter this module."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .fixtures import DYNAMIC_TEXTS, GROUPS, SOURCES, VIDEO_TITLES


class DemoRepository:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        con = sqlite3.connect(self.path, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
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
            if version not in (0, 1):
                raise RuntimeError("Unsupported demo database schema version")
            con.executescript("""
                CREATE TABLE IF NOT EXISTS groups (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sources (
                    uid TEXT PRIMARY KEY, name TEXT NOT NULL,
                    bio TEXT NOT NULL, initials TEXT NOT NULL, color TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memberships (
                    uid TEXT REFERENCES sources(uid),
                    group_id TEXT REFERENCES groups(id),
                    PRIMARY KEY(uid, group_id)
                );
                CREATE TABLE IF NOT EXISTS videos (
                    id TEXT PRIMARY KEY, uid TEXT REFERENCES sources(uid),
                    title TEXT NOT NULL, published_at TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL, description TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dynamics (
                    id TEXT PRIMARY KEY, uid TEXT REFERENCES sources(uid),
                    text TEXT NOT NULL, published_at TEXT NOT NULL, kind TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS memberships_group ON memberships(group_id);
                CREATE INDEX IF NOT EXISTS videos_source ON videos(uid, published_at DESC);
                CREATE INDEX IF NOT EXISTS dynamics_source ON dynamics(uid, published_at DESC);
            """)
            con.executemany("INSERT OR IGNORE INTO groups VALUES (?, ?)", GROUPS)
            for index, (uid, name, bio, initials, color, groups) in enumerate(SOURCES):
                con.execute("INSERT OR IGNORE INTO sources VALUES (?, ?, ?, ?, ?)",
                            (uid, name, bio, initials, color))
                con.executemany("INSERT OR IGNORE INTO memberships VALUES (?, ?)",
                                [(uid, group) for group in groups])
                if index == len(SOURCES) - 1:
                    continue
                for n, title in enumerate(VIDEO_TITLES):
                    con.execute("INSERT OR IGNORE INTO videos VALUES (?, ?, ?, ?, ?, ?)",
                                (f"{uid}-v{n}", uid, title,
                                 f"2026-10-{27 - n:02d}T10:00:00+08:00",
                                 380 + index * 72 + n * 110,
                                 "合成演示视频：用于验证列表、分页与详情展示，不代表实际投稿。"))
                for n, text in enumerate(DYNAMIC_TEXTS):
                    con.execute("INSERT OR IGNORE INTO dynamics VALUES (?, ?, ?, ?, ?)",
                                (f"{uid}-d{n}", uid, text,
                                 f"2026-10-{27 - n:02d}T16:30:00+08:00",
                                 "text" if n != 1 else "video"))
            con.execute("PRAGMA user_version=1")

    def groups(self):
        with self.connection() as con:
            return [dict(row, origin="bilibili_demo") for row in con.execute("""
                SELECT g.id, g.name, COUNT(m.uid) AS member_count
                FROM groups g LEFT JOIN memberships m ON m.group_id=g.id
                GROUP BY g.id ORDER BY g.rowid
            """)]

    @staticmethod
    def _source(con, row):
        source = dict(row)
        uid = source["uid"]
        source["group_ids"] = [r[0] for r in con.execute(
            "SELECT group_id FROM memberships WHERE uid=? ORDER BY group_id", (uid,))]
        source["video_count"] = con.execute("SELECT COUNT(*) FROM videos WHERE uid=?", (uid,)).fetchone()[0]
        source["dynamic_count"] = con.execute("SELECT COUNT(*) FROM dynamics WHERE uid=?", (uid,)).fetchone()[0]
        return source

    def source(self, uid):
        with self.connection() as con:
            row = con.execute("SELECT * FROM sources WHERE uid=?", (uid,)).fetchone()
            return self._source(con, row) if row else None

    def followings(self, group_id, query, offset, limit):
        # instr treats %, _ and quotes literally rather than as LIKE patterns.
        where = "WHERE (instr(s.name, ?) > 0 OR instr(s.bio, ?) > 0)"
        args = [query, query]
        if group_id is not None:
            where += " AND EXISTS (SELECT 1 FROM memberships m WHERE m.uid=s.uid AND m.group_id=?)"
            args.append(group_id)
        with self.connection() as con:
            total = con.execute(f"SELECT COUNT(*) FROM sources s {where}", args).fetchone()[0]
            rows = con.execute(f"SELECT s.* FROM sources s {where} ORDER BY s.uid LIMIT ? OFFSET ?",
                               [*args, limit, offset]).fetchall()
            return [self._source(con, row) for row in rows], total

    def contents(self, uid, kind, offset, limit):
        if kind not in ("videos", "dynamics"):
            raise ValueError("Unsupported content kind")
        with self.connection() as con:
            total = con.execute(f"SELECT COUNT(*) FROM {kind} WHERE uid=?", (uid,)).fetchone()[0]
            rows = con.execute(
                f"SELECT * FROM {kind} WHERE uid=? ORDER BY published_at DESC, id LIMIT ? OFFSET ?",
                (uid, limit, offset)).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                item.pop("uid")
                item["url"] = None
                items.append(item)
            return items, total
