from __future__ import annotations

import json

import pytest

from judge_plausibility import (
    DIMENSIONS,
    evenly_sample,
    load_canonical_judgments,
    parse_json_object,
)


def test_evenly_sample_keeps_endpoints():
    """等距采样必须保留首尾元素。"""
    assert evenly_sample(list(range(10)), 4) == [0, 3, 6, 9]
    assert evenly_sample([1, 2], 4) == [1, 2]


def test_parse_json_object_validates_all_scores():
    """解析器应接受包裹在代码块里的合法 JSON，并拒绝越界分数。"""
    value = {
        "A": {dimension: 4 for dimension in DIMENSIONS},
        "B": {dimension: 3 for dimension in DIMENSIONS},
        "preferred": "A",
        "evidence": {},
        "confidence": "medium",
    }
    assert parse_json_object(f"```json\n{json.dumps(value)}\n```") == value
    value["A"][DIMENSIONS[0]] = 6
    with pytest.raises(ValueError, match="分数非法"):
        parse_json_object(json.dumps(value))


def test_load_canonical_judgments_quarantines_failed_rows(tmp_path):
    """失败的评审行应移入隔离文件，规范文件只保留成功行。"""
    receipts = tmp_path / "plausibility_judgments.jsonl"
    successful = {"persona": "A", "success": True}
    failed = {"persona": "B", "success": False, "error": {"type": "Timeout"}}
    receipts.write_text(
        json.dumps(successful) + "\n" + json.dumps(failed) + "\n",
        encoding="utf-8",
    )

    assert load_canonical_judgments(receipts) == [successful]
    assert receipts.read_text(encoding="utf-8") == json.dumps(successful) + "\n"
    quarantined = list(tmp_path.glob("plausibility_judgments.failed-*.jsonl"))
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text(encoding="utf-8")) == failed
