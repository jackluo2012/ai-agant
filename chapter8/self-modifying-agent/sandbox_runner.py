"""容器入口点。永远不要在可信主机进程中导入此模块。"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import inspect
import json
import sys
from typing import Any

MAX_REQUEST_BYTES = 1024 * 1024
SANDBOX_CHECKS = (
    "public_api_compatible",
    "failure_replay",
    "nonretryable_circuit",
    "temporary_recovery",
    "old_task_regression",
    "canary_ready",
    "rollback_ready",
)


class _NullWriter:
    """空写入器（抑制输出）"""

    def write(self, value: str) -> int:
        return len(value)

    def flush(self) -> None:
        pass


def _namespace(source: str) -> dict[str, Any]:
    """
    从源代码创建命名空间

    Args:
        source: Python 源代码

    Returns:
        包含执行后命名空间的字典
    """
    namespace: dict[str, Any] = {}
    exec(compile(source, "candidate/retry_policy.py", "exec"), namespace)
    return namespace


def _temporary_recovery(namespace: dict[str, Any]) -> bool:
    """
    检查临时超时恢复能力

    Args:
        namespace: 执行命名空间

    Returns:
        如果正确处理临时超时返回 True
    """
    return bool(
        namespace["should_retry"]("TEMPORARY_TIMEOUT", True, 0)
        and namespace["should_retry"]("TEMPORARY_TIMEOUT", True, 1)
    )


def _validate(payload: dict[str, Any]) -> dict[str, bool]:
    """
    验证候选代码

    Args:
        payload: 包含源代码和轨迹的负载

    Returns:
        各项检查的结果字典
    """
    checks = {name: False for name in SANDBOX_CHECKS}
    try:
        namespace = _namespace(payload["source"])
    except Exception:
        return checks
    if not callable(namespace.get("should_retry")) or not callable(
        namespace.get("should_open_circuit")
    ):
        return checks

    try:
        checks["public_api_compatible"] = (
            str(inspect.signature(namespace["should_retry"])) == "(error_code, retryable, attempt)"
            and str(inspect.signature(namespace["should_open_circuit"]))
            == "(consecutive_failures, *, error_code='', retryable=True)"
        )
    except (TypeError, ValueError):
        return checks
    if not checks["public_api_compatible"]:
        return checks

    try:
        failures = [
            item for item in payload["trajectories"] if item.get("outcome") == "failure"
        ]
        checks["failure_replay"] = bool(failures) and all(
            not namespace["should_retry"](item["error_code"], item["retryable"], attempt)
            for item in failures for attempt in range(item["attempts"])
        )
        checks["nonretryable_circuit"] = bool(failures) and all(
            namespace["should_open_circuit"](
                1, error_code=item["error_code"], retryable=item["retryable"]
            )
            for item in failures
        )
        checks["temporary_recovery"] = _temporary_recovery(namespace)
        checks["old_task_regression"] = all((
            namespace["should_retry"]("TEMPORARY_TIMEOUT", True, 0),
            namespace["should_retry"]("TEMPORARY_TIMEOUT", True, 2),
            not namespace["should_retry"]("TEMPORARY_TIMEOUT", True, 3),
            not namespace["should_open_circuit"](
                4, error_code="TEMPORARY_TIMEOUT", retryable=True
            ),
            namespace["should_open_circuit"](
                5, error_code="TEMPORARY_TIMEOUT", retryable=True
            ),
        ))
        checks["canary_ready"] = all((
            not namespace["should_retry"]("AUTH_DENIED", True, 0),
            namespace["should_open_circuit"](
                1, error_code="AUTH_DENIED", retryable=True
            ),
            _temporary_recovery(namespace),
        ))
    except Exception:
        return checks

    stable_source = payload.get("stable_source")
    if stable_source is None:
        checks["rollback_ready"] = True
    else:
        try:
            rollback = _namespace(stable_source)
            checks["rollback_ready"] = bool(
                rollback.get("VERSION") == "1.0.0"
                and rollback["should_retry"]("TEMPORARY_TIMEOUT", True, 0)
                and not rollback["should_retry"]("TEMPORARY_TIMEOUT", True, 3)
            )
        except Exception:
            checks["rollback_ready"] = False
    return checks


def _metrics(payload: dict[str, Any]) -> dict[str, Any]:
    """
    计算候选代码的行为指标

    Args:
        payload: 包含源代码和轨迹的负载

    Returns:
        行为指标字典
    """
    namespace = _namespace(payload["source"])
    failures = [item for item in payload["trajectories"] if item.get("outcome") == "failure"]
    calls = []
    for item in failures:
        made = 1
        while made < item["attempts"] and namespace["should_retry"](
            item["error_code"], item["retryable"], made - 1
        ):
            made += 1
        calls.append(made)
    return {
        "mean_nonretryable_calls": sum(calls) / len(calls) if calls else 0.0,
        "temporary_error_recovery_rate": float(_temporary_recovery(namespace)),
        "old_task_regressions": 0 if all((
            namespace["should_retry"]("TEMPORARY_TIMEOUT", True, 0),
            not namespace["should_retry"]("TEMPORARY_TIMEOUT", True, 3),
        )) else 1,
    }


def main() -> int:
    """
    主入口点（在容器中运行）

    Returns:
        退出码（0 表示成功，非 0 表示错误）
    """
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        return 2
    try:
        payload = json.loads(raw)
        action = payload["action"]
        with redirect_stdout(_NullWriter()), redirect_stderr(_NullWriter()):
            if action == "validate":
                result = {"checks": _validate(payload)}
            elif action == "metrics":
                result = {"metrics": _metrics(payload)}
            else:
                return 2
    except (Exception, SystemExit):
        return 1
    sys.stdout.write(json.dumps({"ok": True, "result": result}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
