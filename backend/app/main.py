"""Local demo API with a separately guarded live metadata cache."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .repository import DemoRepository
from .live_repository import LiveRepository
from .live import BilibiliReader, LiveError, router as live_router
from .follow_sync import FollowingSync

ROOT = Path(__file__).resolve().parents[2]
Mode = Literal["demo", "live"]


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def create_app(db_path: Path | None = None, frontend_path: Path | None = None, live_reader=None,
               live_db_path: Path | None = None):
    repo = DemoRepository(db_path or ROOT / "data" / "demo.sqlite3")
    reader = live_reader or BilibiliReader()
    cache_path = live_db_path or repo.path.with_name("live.sqlite3")
    if cache_path.resolve() == repo.path.resolve():
        raise ValueError("Live and demo databases must use separate files")
    reader.repository = LiveRepository(cache_path)
    reader.sync = FollowingSync(reader)

    @asynccontextmanager
    async def lifespan(app):
        repo.initialize()
        reader.repository.initialize()
        try:
            yield
        finally:
            try:
                await reader.sync.close()
            finally:
                await reader.http.aclose()

    app = FastAPI(title="UP Source Desk Demo", version="0.1.0", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.exception_handler(LiveError)
    async def live_error(request, error):
        return JSONResponse(status_code=error.status, content={"error": {
            "code": error.code, "message": error.message}})

    @app.exception_handler(ApiError)
    async def api_error(request, error):
        return JSONResponse(status_code=error.status,
                            content={"error": {"code": error.code, "message": error.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse(status_code=422, content={"error": {
            "code": "INVALID_PARAMETERS", "message": "请求参数无效，请检查分页与数据模式。"}})

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def require_demo(mode: Mode = "demo"):
        if mode == "live":
            raise ApiError(503, "LIVE_NOT_CONNECTED", "演示接口不提供真实数据。请使用概览上方的独立真实账号接入区。")

    api = APIRouter(prefix="/api", dependencies=[Depends(require_demo)])

    def page(items, total, offset, limit):
        return {"mode": "demo", "items": items,
                "pagination": {"offset": offset, "limit": limit, "total": total,
                               "has_more": offset + len(items) < total},
                "partial": False, "warnings": []}

    def require_source(uid):
        source = repo.source(uid)
        if source is None:
            raise ApiError(404, "SOURCE_NOT_FOUND", "演示数据中不存在该 UP 主。")
        return source

    @api.get("/status")
    def status():
        return {"mode": "demo", "backend": "ready", "storage": "sqlite", "live_available": False}

    @api.get("/account")
    def account():
        _, total = repo.followings(None, "", 0, 1)
        return {"mode": "demo", "account": {"uid": "demo-account", "name": "我的信息源 · 演示账号",
                "auth_state": "demo", "following_count": total, "group_count": len(repo.groups())},
                "warning": "这是合成数据，不是已登录的 B 站账号。"}

    @api.get("/groups")
    def groups():
        items = repo.groups()
        return page(items, len(items), 0, len(items))

    @api.get("/followings")
    def followings(group_id: str | None = None, query: Annotated[str, Query(max_length=200)] = "",
                   offset: Annotated[int, Query(ge=0)] = 0,
                   limit: Annotated[int, Query(ge=1, le=100)] = 20):
        items, total = repo.followings(group_id, query.strip(), offset, limit)
        return page(items, total, offset, limit)

    @api.get("/sources/{uid}")
    def source(uid: str):
        return {"mode": "demo", "source": require_source(uid)}

    @api.get("/sources/{uid}/videos")
    def videos(uid: str, offset: Annotated[int, Query(ge=0)] = 0,
               limit: Annotated[int, Query(ge=1, le=100)] = 20):
        require_source(uid)
        items, total = repo.contents(uid, "videos", offset, limit)
        return page(items, total, offset, limit)

    @api.get("/sources/{uid}/dynamics")
    def dynamics(uid: str, offset: Annotated[int, Query(ge=0)] = 0,
                 limit: Annotated[int, Query(ge=1, le=100)] = 20):
        require_source(uid)
        items, total = repo.contents(uid, "dynamics", offset, limit)
        return page(items, total, offset, limit)

    @api.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def unknown(path: str):
        raise ApiError(404, "API_NOT_FOUND", "接口不存在。演示版不提供修改 B 站账号的操作。")

    app.include_router(live_router(reader))
    app.include_router(api)
    dist = frontend_path if frontend_path is not None else ROOT / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app(Path(os.environ["UPDESK_DB"]) if os.environ.get("UPDESK_DB") else None)
