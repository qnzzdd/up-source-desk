import pytest

from app.policy import (
    CommentMode,
    Depth,
    GroupPolicy,
    ImageMode,
    InferenceMode,
    should_collect,
)


def test_defaults_match_mvp_doc():
    p = GroupPolicy()
    assert p.frequency == "24h"
    assert p.depth == Depth.L1.value
    assert p.comment_mode == CommentMode.OFF.value
    assert p.image_mode == ImageMode.CLASSIFY.value
    assert p.analyze_daily_cap == 1
    assert p.fail_threshold == 3
    assert p.max_tokens_per_cycle == 100_000


def test_monthly_cap_bounds():
    with pytest.raises(ValueError):
        GroupPolicy(analyze_daily_cap=11)
    with pytest.raises(ValueError):
        GroupPolicy(fail_threshold=0)


def test_override_rejects_unknown_field():
    with pytest.raises(ValueError):
        GroupPolicy().merged({"analyze_daliy_cap": 2})
    assert GroupPolicy().merged({"analyze_daily_cap": 2}).analyze_daily_cap == 2


def test_image_promotion_rules():
    p = GroupPolicy(image_mode=ImageMode.ANALYZE.value, analyze_daily_cap=1)
    assert p.image_action("截图", 0) == "analyze"
    assert p.image_action("截图", 1) == "classify"   # 达到日额度
    assert p.image_action("表情包", 0) == "classify"
    assert p.image_action("封面", 0) == "classify"
    assert GroupPolicy(image_mode=ImageMode.OFF.value).image_action("截图", 0) == "off"


def test_comment_trigger():
    p = GroupPolicy(comment_mode=CommentMode.TOP20.value, comment_trigger="views_gt_10000")
    assert p.comment_size_for(9999) == 0
    assert p.comment_size_for(10001) == 20
    assert GroupPolicy(comment_mode=CommentMode.OFF.value).comment_size_for(10**9) == 0


def test_confidence_cap_by_inference():
    assert GroupPolicy(inference=InferenceMode.TITLE.value).confidence_cap() == 0.5
    assert GroupPolicy(inference=InferenceMode.TITLE_COMMENT.value).confidence_cap() == 0.7
    assert GroupPolicy(inference=InferenceMode.WITH_IMAGE.value).confidence_cap() == 0.85


def test_ungrouped_is_never_collected():
    p = GroupPolicy()
    assert should_collect("ungrouped", p) is False
    assert should_collect("paused", p) is False
    assert should_collect("grouped", p) is True
    assert should_collect("grouped", GroupPolicy(state="paused")) is False
