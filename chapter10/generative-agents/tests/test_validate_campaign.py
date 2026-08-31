from __future__ import annotations

from validate_campaign import (
    canonical_provider_receipt,
    compatibility_correction_valid,
    positive_provider_usage,
)


def test_positive_provider_usage_ignores_nested_token_details():
    """用量校验应忽略嵌套的 token 明细，只看总量为正。"""
    row = {
        "response": {
            "usage": {
                "prompt_tokens": 49,
                "prompt_tokens_details": {"cached_tokens": 0},
                "total_tokens": 69,
            }
        }
    }
    assert positive_provider_usage(row) is True


def test_compatibility_correction_must_resolve_to_accessible_arena():
    """兼容性修正必须把输出解析到可达场所列表之内。"""
    row = {
        "kind": "action_arena_compatibility_correction",
        "raw_output": "{Tom and Jane Moreno's bedroom",
        "normalized_output": "Tom and Jane Moreno's bedroom",
        "accessible_arenas": ["common room", "Tom and Jane Moreno's bedroom"],
        "reason": "stripped_response_wrappers",
        "fallback": False,
    }
    assert compatibility_correction_valid(row) is True
    row["normalized_output"] = "private vault"
    assert compatibility_correction_valid(row) is False


def test_failed_compressed_receipts_are_not_canonical(tmp_path):
    """带 .failed- 标记的压缩回执不算规范证据。"""
    assert canonical_provider_receipt(tmp_path / "steps_00000_00360.jsonl.gz")
    assert not canonical_provider_receipt(
        tmp_path / "steps_00000_00360.failed-123.jsonl.gz"
    )
