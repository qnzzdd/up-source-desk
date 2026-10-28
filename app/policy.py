"""分组策略：决定一个 source 被采到什么程度。

设计要点：频率与深度正交；未分组 = 不采集；图片分类先于下载、下载先于分析。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import StrEnum


class Frequency(StrEnum):
    M15 = "15m"
    H1 = "1h"
    H6 = "6h"
    H24 = "24h"
    MANUAL = "manual"

    @property
    def seconds(self) -> int | None:
        return {"15m": 900, "1h": 3600, "6h": 21600, "24h": 86400, "manual": None}[self.value]


class Depth(StrEnum):
    L0 = "L0"  # bvid + 标题 + 发布时间
    L1 = "L1"  # + 封面/时长/播放/简介前 100 字
    L2 = "L2"  # + 热评
    L3 = "L3"  # + 图片处理

    @property
    def rank(self) -> int:
        return int(self.value[1])


class CommentMode(StrEnum):
    OFF = "off"
    TOP10 = "top10"
    TOP20 = "top20"

    @property
    def size(self) -> int:
        return {"off": 0, "top10": 10, "top20": 20}[self.value]


class ImageMode(StrEnum):
    OFF = "off"
    CLASSIFY = "classify"
    DOWNLOAD = "download"
    ANALYZE = "analyze"

    @property
    def rank(self) -> int:
        return {"off": 0, "classify": 1, "download": 2, "analyze": 3}[self.value]


class InferenceMode(StrEnum):
    NONE = "none"
    TITLE = "title"
    TITLE_COMMENT = "title_comment"
    WITH_IMAGE = "with_image"


class GroupState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"


class MonitorState(StrEnum):
    UNGROUPED = "ungrouped"  # 尚未纳入监控：0 次内容请求
    GROUPED = "grouped"
    PAUSED = "paused"        # 用户主动关闭，或连续失败自动暂停


#: 信息量 → 置信度上限（MVP-V1 §6.2）
CONFIDENCE_CAP = {
    InferenceMode.NONE: 0.0,
    InferenceMode.TITLE: 0.5,
    InferenceMode.TITLE_COMMENT: 0.7,
    InferenceMode.WITH_IMAGE: 0.85,
}

#: 图片类别 → 是否值得进入 analyze
ANALYZE_WORTHY = {"截图", "图表", "长图"}
NEVER_ANALYZE = {"表情包", "封面"}


@dataclass(frozen=True)
class GroupPolicy:
    frequency: str = Frequency.H24.value
    depth: str = Depth.L1.value
    comment_mode: str = CommentMode.OFF.value
    comment_trigger: str = "views_gt_10000"
    image_mode: str = ImageMode.CLASSIFY.value
    analyze_daily_cap: int = 1
    inference: str = InferenceMode.TITLE.value
    max_requests_per_cycle: int = 200
    max_tokens_per_cycle: int = 100_000
    fail_threshold: int = 3
    state: str = GroupState.ACTIVE.value

    def __post_init__(self) -> None:
        Frequency(self.frequency)
        Depth(self.depth)
        CommentMode(self.comment_mode)
        ImageMode(self.image_mode)
        InferenceMode(self.inference)
        GroupState(self.state)
        if not 0 <= self.analyze_daily_cap <= 10:
            raise ValueError("analyze_daily_cap 必须在 0..10")
        if not 1 <= self.fail_threshold <= 10:
            raise ValueError("fail_threshold 必须在 1..10")
        if self.max_requests_per_cycle <= 0 or self.max_tokens_per_cycle <= 0:
            raise ValueError("预算必须为正数")

    def to_dict(self) -> dict:
        return asdict(self)

    def merged(self, override: dict | None) -> "GroupPolicy":
        """应用单 UP 覆盖。未知字段直接报错，避免拼写导致的静默失效。"""
        if not override:
            return self
        allowed = set(self.to_dict())
        unknown = set(override) - allowed
        if unknown:
            raise ValueError(f"未知策略字段: {sorted(unknown)}")
        return replace(self, **override)

    # --- 派生判断 ---

    def wants_metadata(self) -> bool:
        return self.depth >= Depth.L0.value

    def wants_description(self) -> bool:
        return Depth(self.depth).rank >= 1

    def comment_size_for(self, view_count: int | None) -> int:
        """按触发条件决定是否拉评论、拉几条。"""
        if CommentMode(self.comment_mode) is CommentMode.OFF:
            return 0
        trig = self.comment_trigger
        if trig == "always":
            return CommentMode(self.comment_mode).size
        if trig.startswith("views_gt_"):
            threshold = int(trig.removeprefix("views_gt_"))
            if view_count is not None and view_count > threshold:
                return CommentMode(self.comment_mode).size
            return 0
        if trig == "title_match":
            return CommentMode(self.comment_mode).size  # 由调用方结合关键词判定
        return 0

    def image_action(self, category: str, analyzed_today: int) -> str:
        """给定图片类别与今日已分析数，返回 off / classify / download / analyze。"""
        mode = ImageMode(self.image_mode)
        if mode is ImageMode.OFF:
            return ImageMode.OFF.value
        if category in NEVER_ANALYZE:
            return ImageMode.CLASSIFY.value
        if mode is ImageMode.CLASSIFY:
            return ImageMode.CLASSIFY.value
        if mode is ImageMode.DOWNLOAD:
            return ImageMode.DOWNLOAD.value
        # mode is ANALYZE
        if category not in ANALYZE_WORTHY:
            return ImageMode.CLASSIFY.value
        if analyzed_today >= self.analyze_daily_cap:
            return ImageMode.CLASSIFY.value
        return ImageMode.ANALYZE.value

    def confidence_cap(self) -> float:
        return CONFIDENCE_CAP[InferenceMode(self.inference)]


def should_collect(monitor_state: str, policy: GroupPolicy) -> bool:
    """唯一的采集准入判断：未分组不进，暂停不进。"""
    return (
        monitor_state == MonitorState.GROUPED.value
        and policy.state == GroupState.ACTIVE.value
    )
