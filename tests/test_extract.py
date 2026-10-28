from __future__ import annotations

import scripts.sync_dynamics as m

draw = {
    "id_str": "1",
    "type": "DYNAMIC_TYPE_DRAW",
    "modules": {
        "module_author": {"pub_ts": 123},
        "module_dynamic": {
            "desc": {"text": "今天拍了张照"},
            "major": {"type": "MAJOR_TYPE_DRAW", "draw": {"items": [
                {"src": "http://x/1.jpg", "width": 1080, "height": 4000},
            ]}},
        },
    },
}
fwd = {
    "id_str": "2",
    "type": "DYNAMIC_TYPE_FORWARD",
    "modules": {"module_author": {"pub_ts": 456}, "module_dynamic": {"desc": {"text": "转发"}}},
}
av = {
    "id_str": "3",
    "type": "DYNAMIC_TYPE_AV",
    "modules": {"module_author": {"pub_ts": 789}, "module_dynamic": {
        "desc": None,
        "major": {"type": "MAJOR_TYPE_AV", "archive": {"bvid": "BV1xx", "title": "新视频"}}}},
}
def test_extract_variants():
    d = m.extract(draw)
    assert d["kind"] == "original" and d["text"] == "今天拍了张照"
    assert len(d["images"]) == 1 and d["images"][0]["height"] == 4000

    f = m.extract(fwd)
    assert f["kind"] == "forward" and f["images"] == []

    a = m.extract(av)
    assert a["kind"] == "video_card" and a["video_bvid"] == "BV1xx"
    assert a["text"] == "新视频"

