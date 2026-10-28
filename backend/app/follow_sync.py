"""Account discovery only: never schedules or fetches creator content."""

import asyncio
from datetime import datetime, timedelta, timezone

from .live import LiveError


def empty_status(uid=None):
    return {"state": "idle", "page": 0, "loaded": 0, "total": 0, "added": 0,
            "last_success": None, "next_run": None, "error": "", "account_uid": uid}


class FollowingSync:
    def __init__(self, reader, refresh_seconds=600, page_size=50, max_pages=1000):
        self.reader = reader
        self.refresh_seconds = refresh_seconds
        self.page_size = page_size
        self.max_pages = max_pages
        self.task = None
        self.progress = empty_status()

    @property
    def running(self):
        return self.task is not None and not self.task.done() and self.progress["state"] == "running"

    def status(self, uid):
        if uid is None:
            return empty_status()
        if self.progress["account_uid"] == uid:
            return dict(self.progress)
        return self.reader.local_operation("load_sync", uid) or empty_status(uid)

    def _save(self):
        self.reader.local_operation("save_sync", self.progress["account_uid"], self.progress)

    async def start(self):
        self.reader.require_account()
        uid = self.reader.account["uid"]
        if self.running and self.progress["account_uid"] == uid:
            return dict(self.progress)
        previous_task = self.task
        self.task = None
        if previous_task and not previous_task.done():
            previous_task.cancel()
            try:
                await previous_task
            except asyncio.CancelledError:
                pass
        previous = self.status(uid)
        self.progress = {**empty_status(uid), "state": "running", "last_success": previous["last_success"]}
        self._save()
        self.task = asyncio.create_task(self._loop(uid))
        return dict(self.progress)

    def stop(self, reason):
        if self.task and not self.task.done():
            self.task.cancel()
            self.progress.update(state="stopped", next_run=None, error=reason)
            try:
                self._save()
            except LiveError:
                self.progress["error"] += " 同步状态写盘失败。"

    async def close(self):
        try:
            self.stop("服务已停止，登录后重新同步。")
        except LiveError:
            pass
        if self.task:
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def _check_account(self, uid):
        if not self.reader.account or self.reader.account["uid"] != uid or not self.reader.cookie:
            raise LiveError("LOGIN_REQUIRED", "登录已失效或账号已切换，自动同步已停止。", 401)

    async def _loop(self, uid):
        try:
            while True:
                complete = await self._sweep(uid)
                if not complete:
                    return
                await asyncio.sleep(self.refresh_seconds)
                self._check_account(uid)
                self.progress.update(state="running", page=0, loaded=0, total=0, added=0, next_run=None, error="")
                self._save()
        except asyncio.CancelledError:
            raise
        except LiveError as error:
            self.progress.update(state="error", next_run=None, error=f"{error.code} · {error.message}")
            try:
                self._save()
            except LiveError:
                pass
        except Exception:
            self.progress.update(state="error", next_run=None, error="同步异常，已停止自动请求；请手动重试。")
            try:
                self._save()
            except LiveError:
                pass

    async def _sweep(self, uid):
        self._check_account(uid)
        known = {r["uid"] for r in self.reader.local_operation("load", uid)["items"]}
        seen = set()
        total = None
        for page in range(1, self.max_pages + 1):
            self._check_account(uid)
            result = await self.reader.following_page(page, self.page_size)
            ids = {r["uid"] for r in result["items"]}
            new = ids - seen
            changed = total is not None and total != result["total"]
            total = result["total"] if total is None else total
            seen.update(ids)
            self.reader.allowed.update(ids)
            self.progress.update(page=page, loaded=len(seen), total=total, added=len(seen - known))
            if changed or total < 0 or len(seen) > total:
                self.progress.update(state="incomplete", error="读取期间关注总数发生变化或计数异常；已保存部分数据，请手动重新同步。", next_run=None)
                self._save()
                return False
            if len(seen) == total:
                # Native groups are metadata, not monitoring configuration.
                await self.reader.groups()
                now = datetime.now(timezone.utc)
                self.progress.update(state="complete", last_success=now.isoformat(),
                                     next_run=(now + timedelta(seconds=self.refresh_seconds)).isoformat(), error="")
                self._save()
                return True
            if not new:
                self.progress.update(state="incomplete", error="分页返回空页或重复页，尚未读取全部关注；自动同步已停止。", next_run=None)
                self._save()
                return False
            self._save()
            # Give status/local requests a scheduling window between remote pages.
            await asyncio.sleep(0.01)
        self.progress.update(state="incomplete", error="达到分页安全上限，未视为完整同步。", next_run=None)
        self._save()
        return False
