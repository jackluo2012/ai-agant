"""由 `domain_spec.json` 配置的确定性策略记录适配器。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


def _spec() -> dict[str, Any]:
    """
    加载领域规范配置

    Returns:
        领域规范字典
    """
    with (ROOT / "domain_spec.json").open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("domain_spec.json 必须包含一个对象")
    return value


def evaluate_policy_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """
    评估策略记录

    Args:
        records: 待评估的记录列表

    Returns:
        评估结果字典，包含审批状态、决策、评估数量、失败记录等
    """
    spec = _spec()
    required_field = spec["required_field"]
    status_field = spec["status_field"]
    identifier_field = spec["identifier_field"]
    evidence_field = spec["evidence_field"]
    passing = {str(value).casefold() for value in spec["passing_values"]}
    remediation = {
        str(key).casefold(): value
        for key, value in spec["remediation_by_status"].items()
    }
    failures: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []

    # 遍历所有记录进行评估
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"记录 {index} 必须是一个对象")

        # 检查必需字段
        missing = [
            field
            for field in (identifier_field, required_field, status_field, evidence_field)
            if field not in record
        ]
        if missing:
            raise ValueError(f"记录 {index} 缺少字段：{', '.join(missing)}")

        # 验证必需字段类型
        if not isinstance(record[required_field], bool):
            raise ValueError(f"记录 {index} 的 {required_field} 必须是布尔值")

        # 评估记录状态
        status = str(record[status_field])
        row = {
            "id": record[identifier_field],
            "required": record[required_field],
            "status": status,
            "evidence": record[evidence_field],
            "passed": status.casefold() in passing,
        }
        normalized.append(row)

        # 收集失败的必需记录
        if row["required"] and not row["passed"]:
            failures.append(
                {
                    **row,
                    "remediation": remediation.get(
                        status.casefold(), spec["default_remediation"]
                    ),
                }
            )

    # 确定最终决策
    approved = not failures
    return {
        "approved": approved,
        "decision": spec["approved_label"] if approved else spec["rejected_label"],
        "evaluated_count": len(normalized),
        "failed_required_count": len(failures),
        "failed_required_records": failures,
        "records": normalized,
    }


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    执行工具调用

    Args:
        name: 工具名称
        arguments: 工具参数

    Returns:
        工具执行结果，包含 ok 状态和 result 或 error
    """
    spec = _spec()
    if name == spec["tool_name"]:
        records = arguments.get(spec["records_argument"])
        if not isinstance(records, list) or not records:
            return {
                "ok": False,
                "error": f"{spec['records_argument']} 必须是非空数组",
            }
        try:
            return {"ok": True, "result": evaluate_policy_records(records)}
        except (KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": f"未知工具：{name}"}
