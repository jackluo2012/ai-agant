"""测试发布门槛检查对非字典编辑项的处理"""
import pytest

# 添加项目根目录到路径
import sys
import os
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from release_gate import evaluate_release_gate


def test_evaluate_release_gate_non_dict_edit_item():
    """测试当编辑数组中包含非字典项时，发布门槛应拒绝候选版本"""
    before = {"holdout": (5, 10), "boundary": (3, 5)}
    after = {"holdout": (5, 10), "boundary": (4, 5)}
    manifest = {
        "diff": "diff text",
        "edits": [None, "string_edit", {"old_str": "a", "new_str": "b"}],
        "source_case_ids": ["1"],
    }
    result = evaluate_release_gate(before, after, manifest)
    assert result["accepted"] is False
    assert result["checks"]["patch_is_auditable_old_to_new_edit"] is False
    assert result["decision"] == "reject_candidate"
