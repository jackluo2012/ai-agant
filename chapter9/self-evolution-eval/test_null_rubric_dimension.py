"""评估 JSON null 的评分维度必须计为 0，而非 int(None)。"""

import sys
import os

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

import pytest

from harness import _rubric_dimension_total


def test_null_rubric_dimension_coerced():
    """
    测试 null 评分维度被强制为 0

    验证包含 None 值的评分能正确计算总分
    """
    rubric = {
        "error_handling": None,
        "input_validation": 2,
        "documentation": 1,
        "robustness": 3,
        "comment": "ok",
    }
    assert _rubric_dimension_total(rubric) == 6


def test_missing_dimension_still_zero():
    """
    测试缺失的维度计为 0

    验证缺少某些维度时仍能正确计算总分
    """
    assert _rubric_dimension_total({"input_validation": 3}) == 3


def test_empty_string_score_rejected():
    """
    测试空字符串分数被拒绝

    验证空字符串会引发 ValueError
    """
    with pytest.raises(ValueError):
        _rubric_dimension_total({"error_handling": ""})
