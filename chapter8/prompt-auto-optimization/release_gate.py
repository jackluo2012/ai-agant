"""提示词候选版本的清单与发布门槛检查。"""

from __future__ import annotations

from typing import Any, Dict


def build_candidate_manifest(
    optimization: Dict[str, Any], learning_signal: Dict[str, Any]
) -> Dict[str, Any]:
    """
    构建候选提示词的清单

    Args:
        optimization: Coding Agent 的优化结果
        learning_signal: 失败轨迹诊断生成的学习信号

    Returns:
        包含候选版本信息的清单字典
    """
    return {
        "artifact_type": "system_prompt_patch",
        "source_case_ids": list(learning_signal.get("source_case_ids", [])),
        "scope": learning_signal.get("scope", "system_prompt"),
        "rationale": optimization.get("rationale") or learning_signal.get("diagnosis", ""),
        "diff": optimization.get("diff", ""),
        "edits": list(optimization.get("edits", [])),
        "target_rule": "仅在明确要求人工或紧急安全事件时转接；其他情况需解释政策并提供合规替代方案",
        "status": "candidate",
    }


def evaluate_release_gate(
    before: Dict[str, Any], after: Dict[str, Any], manifest: Dict[str, Any]
) -> Dict[str, Any]:
    """
    评估候选版本是否通过发布门槛

    发布门槛包含四个条件：
    1. patch_is_nonempty: 补丁非空
    2. patch_is_auditable_old_to_new_edit: 补丁可审计（包含精确的 old->new 编辑）
    3. source_cases_are_recorded: 来源用例已记录
    4. holdout_did_not_regress: 保留任务集未退化
    5. boundary_improved: 边界案例集有改善

    Args:
        before: 优化前的评估结果
        after: 优化后的评估结果
        manifest: 候选版本清单

    Returns:
        包含发布决定和详细检查结果的字典
    """
    holdout_before, holdout_total = before["holdout"]
    holdout_after, _ = after["holdout"]
    boundary_before, boundary_total = before["boundary"]
    boundary_after, _ = after["boundary"]

    checks = {
        "patch_is_nonempty": bool(manifest.get("diff", "").strip()),
        "patch_is_auditable_old_to_new_edit": bool(manifest.get("edits")) and all(
            isinstance(edit, dict)
            and isinstance(edit.get("old_str"), str) and bool(edit["old_str"])
            and isinstance(edit.get("new_str"), str) and bool(edit["new_str"])
            for edit in manifest.get("edits", [])
        ),
        "source_cases_are_recorded": bool(manifest.get("source_case_ids")),
        "holdout_did_not_regress": holdout_after >= holdout_before,
        "boundary_improved": boundary_after > boundary_before,
    }

    accepted = all(checks.values())

    return {
        "decision": "release_to_canary" if accepted else "reject_candidate",
        "accepted": accepted,
        "checks": checks,
        "metrics": {
            "holdout_before": [holdout_before, holdout_total],
            "holdout_after": [holdout_after, holdout_total],
            "boundary_before": [boundary_before, boundary_total],
            "boundary_after": [boundary_after, boundary_total],
        },
    }
