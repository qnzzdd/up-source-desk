"""运行配置。凭据只从环境变量/本地文件读取，绝不写入代码库。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "upsd.sqlite3"


@dataclass(frozen=True)
class Settings:
    db_path: Path
    cookie: str
    user_agent: str
    request_interval: float
    max_retries: int

    @property
    def has_cookie(self) -> bool:
        return bool(self.cookie.strip())


def load_cookie() -> str:
    """优先级：BILI_COOKIE 环境变量 > 本地 cookie.txt（不应提交）。"""
    env = os.environ.get("BILI_COOKIE", "").strip()
    if env:
        return env
    path = BASE_DIR / "cookie.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def load_settings() -> Settings:
    return Settings(
        db_path=Path(os.environ.get("UPSD_DB", DEFAULT_DB_PATH)),
        cookie=load_cookie(),
        user_agent=os.environ.get(
            "UPSD_UA",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        ),
        request_interval=float(os.environ.get("UPSD_INTERVAL", "1.0")),
        max_retries=int(os.environ.get("UPSD_RETRIES", "3")),
    )
