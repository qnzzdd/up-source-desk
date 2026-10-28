"""数据模型。字段含义见 docs/MVP-V1.md §7。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Group(Base):
    """分组即策略：采集行为的唯一来源。"""

    __tablename__ = "grp"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # --- 策略字段（默认值见 app/policy.py） ---
    frequency: Mapped[str] = mapped_column(String(16), default="24h")
    depth: Mapped[str] = mapped_column(String(4), default="L1")
    comment_mode: Mapped[str] = mapped_column(String(8), default="off")
    comment_trigger: Mapped[str] = mapped_column(String(24), default="views_gt_10000")
    image_mode: Mapped[str] = mapped_column(String(12), default="classify")
    analyze_daily_cap: Mapped[int] = mapped_column(Integer, default=1)
    inference: Mapped[str] = mapped_column(String(16), default="title")
    max_requests_per_cycle: Mapped[int] = mapped_column(Integer, default=200)
    max_tokens_per_cycle: Mapped[int] = mapped_column(Integer, default=100_000)
    fail_threshold: Mapped[int] = mapped_column(Integer, default=3)
    state: Mapped[str] = mapped_column(String(8), default="active")

    sources: Mapped[list["Source"]] = relationship(back_populates="group")


class Source(Base):
    """一个被关注的 UP 主。monitor_state 与 paused 语义分开。"""

    __tablename__ = "source"

    id: Mapped[int] = mapped_column(primary_key=True)
    mid: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    uname: Mapped[str] = mapped_column(String(128))
    face: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sign: Mapped[str | None] = mapped_column(Text, nullable=True)

    group_id: Mapped[int | None] = mapped_column(ForeignKey("grp.id"), nullable=True)
    # ungrouped | grouped | paused
    monitor_state: Mapped[str] = mapped_column(String(12), default="ungrouped")
    is_followed: Mapped[bool] = mapped_column(Boolean, default=True)

    follow_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    paused_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    group: Mapped[Group | None] = relationship(back_populates="sources")
    name_history: Mapped[list["SourceNameHistory"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class SourceNameHistory(Base):
    __tablename__ = "source_name_history"
    __table_args__ = (UniqueConstraint("source_id", "uname", name="uq_name_hist"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"))
    uname: Mapped[str] = mapped_column(String(128))
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    source: Mapped[Source] = relationship(back_populates="name_history")


class VideoMeta(Base):
    """只存元数据，不下载视频。"""

    __tablename__ = "video_meta"

    id: Mapped[int] = mapped_column(primary_key=True)
    bvid: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    aid: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pubdate: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    view_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    desc_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform_status: Mapped[str] = mapped_column(String(16), default="normal")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CommentSample(Base):
    __tablename__ = "comment_sample"

    id: Mapped[int] = mapped_column(primary_key=True)
    bvid: Mapped[str] = mapped_column(String(24), index=True)
    sample_size: Mapped[int] = mapped_column(Integer)
    # 只存评论正文，绝不存作者昵称/mid/头像
    texts: Mapped[list] = mapped_column(JSON, default=list)
    filter_version: Mapped[str] = mapped_column(String(16), default="v1")
    sampled_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Inference(Base):
    __tablename__ = "inference"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "input_hash", name="uq_inference"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(12))  # video | dynamic
    target_id: Mapped[str] = mapped_column(String(32), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(16), default="v1")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DynamicPost(Base):
    __tablename__ = "dynamic_post"

    id: Mapped[int] = mapped_column(primary_key=True)
    dynamic_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="original")
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    pubdate: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MediaAsset(Base):
    __tablename__ = "media_asset"
    __table_args__ = (UniqueConstraint("image_hash", name="uq_media_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    image_hash: Mapped[str] = mapped_column(String(64), index=True)
    owner_type: Mapped[str] = mapped_column(String(12))
    owner_id: Mapped[str] = mapped_column(String(32), index=True)
    url: Mapped[str] = mapped_column(String(512))
    category: Mapped[str] = mapped_column(String(16), default="unknown")
    category_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    downloaded: Mapped[bool] = mapped_column(Boolean, default=False)
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False)
    local_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ImageAnalysis(Base):
    __tablename__ = "image_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)
    media_asset_id: Mapped[int] = mapped_column(ForeignKey("media_asset.id"))
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(64))
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SyncCursor(Base):
    """必须区分：ok（有数据）/ empty（确实没有）/ invalid（游标失效）/ failed。"""

    __tablename__ = "sync_cursor"
    __table_args__ = (UniqueConstraint("source_id", "kind", name="uq_cursor"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"))
    kind: Mapped[str] = mapped_column(String(16))  # video | dynamic | follow
    last_pubdate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_bvid: Mapped[str | None] = mapped_column(String(24), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class JobRun(Base):
    __tablename__ = "job_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(24))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("source.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Report(Base):
    __tablename__ = "report"
    __table_args__ = (UniqueConstraint("date", "group_id", name="uq_report"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(String(10))  # Asia/Shanghai 自然日
    group_id: Mapped[int] = mapped_column(ForeignKey("grp.id"))
    state: Mapped[str] = mapped_column(String(12), default="pending")
    path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    coverage: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PolicyOverride(Base):
    """单个 UP 覆盖分组策略中任意字段。"""

    __tablename__ = "source_policy_override"
    __table_args__ = (UniqueConstraint("source_id", name="uq_override"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"))
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
