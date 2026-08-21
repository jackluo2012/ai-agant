"""实验 8-5 的可审计自我修改和可信发布门控。"""

from __future__ import annotations

import ast
from collections import defaultdict
import difflib
import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable

# 添加项目根目录到路径
import os
import sys
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from candidate_sandbox import MAX_SOURCE_BYTES, SandboxError, run_in_sandbox


OLD_CODES = 'NON_RETRYABLE_CODES = {"AUTH_DENIED", "INVALID_ARGUMENT"}'
NEW_CODES = 'NON_RETRYABLE_CODES = {"AUTH_DENIED", "INVALID_ARGUMENT", "PAYMENT_DECLINED"}'

OLD_RETRY = '''def should_retry(error_code, retryable, attempt):
    """Return whether another tool call should be attempted."""
    return attempt < MAX_RETRIES
'''
NEW_RETRY = '''def should_retry(error_code, retryable, attempt):
    """Return whether another tool call should be attempted."""
    if not retryable or error_code in NON_RETRYABLE_CODES:
        return False
    return attempt < MAX_RETRIES
'''

OLD_BREAKER = '''def should_open_circuit(consecutive_failures, *, error_code="", retryable=True):
    """Open after repeated failures."""
    return consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD
'''
NEW_BREAKER = '''def should_open_circuit(consecutive_failures, *, error_code="", retryable=True):
    """Open immediately for permanent errors; otherwise use the threshold."""
    if not retryable or error_code in NON_RETRYABLE_CODES:
        return consecutive_failures >= 1
    return consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD
'''

CHECK_NAMES = (
    "static_compile",
    "security_scan",
    "sandbox_execution",
    "public_api_compatible",
    "failure_replay",
    "nonretryable_circuit",
    "temporary_recovery",
    "old_task_regression",
    "canary_ready",
    "rollback_ready",
)


def sha256_text(source: str) -> str:
    """
    计算文本的 SHA256 哈希值

    Args:
        source: 待哈希的文本

    Returns:
        SHA256 哈希值（十六进制字符串）
    """
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _short_sha(source: str) -> str:
    """
    获取文本的短 SHA256 哈希值（前 12 位）

    Args:
        source: 待哈希的文本

    Returns:
        短哈希值（前 12 位十六进制字符）
    """
    return sha256_text(source)[:12]


def diagnose(trajectories: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """
    诊断失败轨迹中的模式

    Args:
        trajectories: 失败轨迹的可迭代对象

    Returns:
        诊断结果字典，包含是否需要修改、目标组件、源案例等信息
    """
    trajectories = list(trajectories)
    repeated: Dict[tuple[str, str], list[Dict[str, Any]]] = defaultdict(list)
    for item in trajectories:
        # 检查重复的非可重试失败
        if item.get("outcome") == "failure" and not item.get("retryable", True) and item.get("attempts", 0) > 1:
            repeated[(item.get("tool", ""), item.get("error_code", ""))].append(item)

    patterns = []
    for (tool, error_code), items in repeated.items():
        if len(items) >= 2:
            patterns.append({
                "cluster_id": f"{tool}:{error_code}",
                "tool": tool,
                "error_code": error_code,
                "source_case_ids": [item["id"] for item in items],
                "cross_trajectory_support": len(items),
                "total_redundant_calls": sum(item["attempts"] - 1 for item in items),
            })
    if not patterns:
        return {
            "change_required": False,
            "target": None,
            "source_case_ids": [],
            "reason": "No repeated non-retryable failure pattern has enough support.",
        }
    source_ids = sorted({case_id for pattern in patterns for case_id in pattern["source_case_ids"]})
    sources = [
        {
            "id": item["id"],
            "trajectory_sha256": sha256_text(repr(sorted(item.items()))),
            "evidence": item.get("evidence"),
        }
        for item in trajectories if item.get("id") in source_ids
    ]
    return {
        "change_required": True,
        "target": "stable/retry_policy.py",
        "target_component": "retry_and_circuit_breaker_control",
        "source_case_ids": source_ids,
        "source_trajectories": sources,
        "patterns": patterns,
        "reason": (
            "The deterministic control policy ignores retryable=false and does not open the circuit "
            "for permanent errors. The root cause belongs in retry/circuit-breaker code, not a prompt."
        ),
        "change_contract": {
            "expected_fix": [
                "non-retryable tool-call attempts fall to one",
                "the circuit opens on the first permanent failure",
            ],
            "potential_regressions": [
                "temporary timeouts stop retrying",
                "the five-failure circuit threshold changes for retryable errors",
                "public function signatures change",
            ],
        },
    }


def _replace_once(source: str, old: str, new: str) -> str:
    """
    替换源代码中的一个匹配项

    Args:
        source: 源代码
        old: 待替换的旧文本
        new: 新文本

    Returns:
        替换后的源代码

    Raises:
        ValueError: 如果旧文本不恰好匹配一次
    """
    if source.count(old) != 1:
        raise ValueError("候选补丁不再精确匹配一个稳定代码区域")
    return source.replace(old, new, 1)


def candidate_from_source(
    stable_source: str,
    candidate_source: str,
    *,
    impact_prediction: Dict[str, Any] | None = None,
    generator_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    将生成的源代码和来源信息打包为可审查的候选

    Args:
        stable_source: 稳定版本的源代码
        candidate_source: 候选版本的源代码
        impact_prediction: 影响预测（可选）
        generator_metadata: 生成器元数据（可选）

    Returns:
        包含候选信息、差异、影响预测等的字典
    """
    diff = "".join(difflib.unified_diff(
        stable_source.splitlines(keepends=True),
        candidate_source.splitlines(keepends=True),
        fromfile="stable/retry_policy.py",
        tofile="candidate/retry_policy.py",
    ))
    added = sum(line.startswith("+") and not line.startswith("+++") for line in diff.splitlines())
    deleted = sum(line.startswith("-") and not line.startswith("---") for line in diff.splitlines())
    return {
        "source": candidate_source,
        "diff": diff,
        "changed": candidate_source != stable_source,
        "impact_prediction": impact_prediction or {},
        "generator_metadata": generator_metadata or {},
        "source_sha256": sha256_text(candidate_source),
        "patch_size": {"added_lines": added, "deleted_lines": deleted, "changed_lines": added + deleted},
    }


def generate_candidate(stable_source: str, diagnosis: Dict[str, Any]) -> Dict[str, Any]:
    """
    生成确定性比较候选（不修改稳定版本）

    Args:
        stable_source: 稳定版本的源代码
        diagnosis: 失败诊断信息

    Returns:
        候选代码字典
    """
    if not diagnosis.get("change_required"):
        return candidate_from_source(stable_source, stable_source)
    candidate = _replace_once(stable_source, OLD_CODES, NEW_CODES)
    candidate = _replace_once(candidate, OLD_RETRY, NEW_RETRY)
    candidate = _replace_once(candidate, OLD_BREAKER, NEW_BREAKER)
    candidate = candidate.replace('VERSION = "1.0.0"', 'VERSION = "1.1.0-candidate"', 1)
    return candidate_from_source(
        stable_source,
        candidate,
        impact_prediction={
            "non_retryable_calls": {"before": "up to 4", "after": 1},
            "temporary_timeout_recovery_rate": {"before": 1.0, "after": 1.0},
        },
        generator_metadata={"generator": "deterministic", "model": None, "api_calls": 0},
    )


def generate_rejected_control(stable_source: str, diagnosis: Dict[str, Any]) -> Dict[str, Any]:
    """
    生成看起来像历史的错误补丁（通过禁用所有重试来修复事件）

    Args:
        stable_source: 稳定版本的源代码
        diagnosis: 失败诊断信息

    Returns:
        被拒绝的控制候选字典
    """
    candidate = _replace_once(stable_source, OLD_RETRY, '''def should_retry(error_code, retryable, attempt):
    """Incorrect over-broad fix retained as a rejected candidate."""
    return False
''')
    candidate = _replace_once(candidate, OLD_BREAKER, NEW_BREAKER)
    candidate = candidate.replace('VERSION = "1.0.0"', 'VERSION = "1.0.1-rejected"', 1)
    return candidate_from_source(
        stable_source,
        candidate,
        impact_prediction={
            "non_retryable_calls": {"after": 1},
            "temporary_timeout_recovery_rate": {"after": 0.0},
        },
        generator_metadata={"generator": "negative_control", "api_calls": 0},
    )


def _safe_ast(source: str) -> bool:
    """
    在沙箱执行前应用快速深度防御过滤器

    Args:
        source: 待检查的源代码

    Returns:
        如果源代码通过安全检查返回 True，否则返回 False
    """
    tree = ast.parse(source)
    forbidden_calls = {"eval", "exec", "compile", "open", "__import__"}
    return not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        or (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in forbidden_calls)
        for node in ast.walk(tree)
    )


def validate_candidate(
    candidate_source: str,
    trajectories: Iterable[Dict[str, Any]],
    stable_source: str | None = None,
) -> Dict[str, bool]:
    """
    在 Docker 中执行候选代码以运行发布门控

    Args:
        candidate_source: 候选版本的源代码
        trajectories: 失败轨迹的可迭代对象
        stable_source: 稳定版本的源代码（可选）

    Returns:
        各项检查的结果字典
    """
    checks = {name: False for name in CHECK_NAMES}
    try:
        oversized = len(candidate_source.encode("utf-8")) > MAX_SOURCE_BYTES
    except UnicodeError:
        return checks
    if oversized:
        return checks
    try:
        # Compilation and the AST scan do not execute the source. The scan is a
        # fast prefilter; the container, not this deny-list, is the security boundary.
        compile(candidate_source, "candidate/retry_policy.py", "exec")
        checks["static_compile"] = True
        checks["security_scan"] = _safe_ast(candidate_source)
        if not checks["security_scan"]:
            return checks
    except Exception:
        return checks

    try:
        result = run_in_sandbox(
            "validate",
            candidate_source,
            trajectories,
            stable_source=stable_source,
        )
    except SandboxError:
        return checks
    sandbox_checks = result.get("checks")
    if not isinstance(sandbox_checks, dict):
        return checks
    checks["sandbox_execution"] = True
    for name in CHECK_NAMES:
        if name not in {"static_compile", "security_scan", "sandbox_execution"}:
            checks[name] = sandbox_checks.get(name) is True
    return checks


def behavior_metrics(candidate_source: str, trajectories: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """
    在同一个锁定的沙箱中测量候选行为

    Args:
        candidate_source: 候选版本的源代码
        trajectories: 失败轨迹的可迭代对象

    Returns:
        行为指标字典，包括平均非可重试调用次数、临时错误恢复率等
    """
    try:
        result = run_in_sandbox("metrics", candidate_source, trajectories)
    except SandboxError:
        return {
            "mean_nonretryable_calls": None,
            "temporary_error_recovery_rate": None,
            "old_task_regressions": None,
            "evaluation_failed": True,
        }
    metrics = result.get("metrics")
    if not isinstance(metrics, dict):
        return {
            "mean_nonretryable_calls": None,
            "temporary_error_recovery_rate": None,
            "old_task_regressions": None,
            "evaluation_failed": True,
        }
    return metrics


def release_manifest(
    stable_source: str,
    candidate: Dict[str, Any],
    diagnosis: Dict[str, Any],
    checks: Dict[str, bool],
    *,
    provenance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    生成发布清单

    Args:
        stable_source: 稳定版本的源代码
        candidate: 候选代码字典
        diagnosis: 失败诊断信息
        checks: 检查结果字典
        provenance: 来源信息（可选）

    Returns:
        发布清单字典，包含所有发布门控结果
    """
    accepted = candidate.get("changed", False) and bool(checks) and all(checks.values())
    failed = [name for name, passed in checks.items() if not passed]
    contract = diagnosis.get("change_contract", {})
    return {
        "artifact_type": "agent_control_code_patch",
        "failure_cluster": diagnosis.get("patterns", []),
        "source_trajectories": diagnosis.get("source_trajectories", []),
        "inferred_root_cause": diagnosis.get("reason"),
        "target_component": diagnosis.get("target_component"),
        "target_file": diagnosis.get("target"),
        "code_diff": candidate.get("diff", ""),
        "impact_prediction": candidate.get("impact_prediction", {}),
        "expected_fix": contract.get("expected_fix", []),
        "potential_regressions": contract.get("potential_regressions", []),
        "stable_version": _short_sha(stable_source),
        "stable_sha256": sha256_text(stable_source),
        "candidate_version": _short_sha(candidate.get("source", stable_source)),
        "candidate_sha256": sha256_text(candidate.get("source", stable_source)),
        "rollback_version": _short_sha(stable_source),
        "rollback_sha256": sha256_text(stable_source),
        # Compatibility field retained for readers of the earlier demo.
        "diff": candidate.get("diff", ""),
        "patch_size": candidate.get("patch_size", {}),
        "checks": checks,
        "failed_checks": failed,
        "canary_gate": {
            "eligible": accepted,
            "scope": "shadow traffic only; stable remains unchanged",
            "rollback_trigger": "any non-retryable repeat or temporary-recovery regression",
        },
        "rollback_gate": {
            "artifact_hash_matches_stable": checks.get("rollback_ready", False),
            "rollback_version": _short_sha(stable_source),
        },
        "provenance": provenance or candidate.get("generator_metadata", {}),
        "decision": "release_to_canary" if accepted else "reject_candidate",
        "rejection_reason": None if accepted else (
            "candidate did not change stable source" if not candidate.get("changed")
            else "failed gates: " + ", ".join(failed)
        ),
    }


def write_candidate(candidate_source: str, path: Path) -> None:
    """
    仅写入候选制品路径，绝不覆盖稳定模块

    Args:
        candidate_source: 候选版本的源代码
        path: 目标文件路径
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(candidate_source, encoding="utf-8")
