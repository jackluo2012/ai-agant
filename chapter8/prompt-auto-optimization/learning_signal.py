"""将评估的客服轨迹转换为提示词学习信号。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict


# 三维评估维度
DIMENSIONS = ("rule_compliance", "task_resolution", "compliant_flexibility")


def case_dimensions(result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    从单个用例结果中提取三维评估数据

    Args:
        result: 单个用例的评估结果

    Returns:
        包含三个维度评估结果的字典：
        - rule_compliance: 规则合规性（是否遵守强制规则）
        - task_resolution: 任务解决情况（是否正确处理请求）
        - compliant_flexibility: 合规灵活性（政策争议时的处理方式）
    """
    should_transfer = bool(result["should_transfer"])
    transferred = bool(result["transferred"])
    boundary = result["group"] == "boundary"
    correct = bool(result["correct"])

    # 规则合规性检查
    if should_transfer and not transferred:
        compliance = {
            "verdict": "fail",
            "evidence": "Required escalation boundary was ignored",
        }
    else:
        compliance = {
            "verdict": "pass",
            "evidence": "No forbidden action or missed mandatory escalation was observed",
        }

    # 任务解决情况
    resolution = {
        "verdict": "pass" if correct else "fail",
        "evidence": result.get("note", ""),
    }

    # 合规灵活性（仅针对边界案例集）
    if boundary:
        flexible = not transferred and bool(result.get("handled"))
        flexibility = {
            "verdict": "pass" if flexible else "fail",
            "evidence": (
                "Explained policy and supplied an allowed alternative"
                if flexible
                else "Policy dispute was transferred or left without a useful compliant alternative"
            ),
        }
    else:
        flexibility = {
            "verdict": "pass",
            "evidence": "This case does not require a blocked-path alternative",
        }

    return {
        "rule_compliance": compliance,
        "task_resolution": resolution,
        "compliant_flexibility": flexibility,
    }


def diagnose_failures(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    """
    将失败的用例聚合成带证据的改进请求

    Args:
        evaluation: 完整的评估结果

    Returns:
        包含诊断信息的字典：
        - source_case_ids: 来源用例 ID 列表
        - scope: 影响范围
        - dimensions: 按维度分组的失败用例
        - diagnosis: 诊断结论
        - case_reports: 所有用例的报告
    """
    failed_by_dimension: Dict[str, list[Dict[str, str]]] = defaultdict(list)
    all_case_reports = []

    for result in evaluation.get("results", []):
        dimensions = case_dimensions(result)
        all_case_reports.append({"case_id": result["id"], "dimensions": dimensions})

        # 收集失败的维度
        for dimension, verdict in dimensions.items():
            if verdict["verdict"] == "fail":
                failed_by_dimension[dimension].append({
                    "case_id": result["id"],
                    "evidence": verdict["evidence"],
                })

    # 提取失败用例 ID
    source_ids = sorted({
        item["case_id"]
        for failures in failed_by_dimension.values()
        for item in failures
    })

    # 提取边界集失败用例（过度转接问题）
    boundary_ids = [
        item["case_id"]
        for item in failed_by_dimension.get("compliant_flexibility", [])
    ]

    # 生成诊断结论
    diagnosis = (
        "The prompt over-escalates policy disputes. Preserve mandatory escalation for explicit "
        "human requests and safety emergencies, but require policy explanation and an allowed "
        "alternative before transfer in ordinary disputes."
        if boundary_ids
        else "No repeated prompt-level boundary failure was detected."
    )

    return {
        "source_case_ids": source_ids,
        "scope": "system_prompt.transfer_policy",
        "dimensions": {dimension: failed_by_dimension.get(dimension, []) for dimension in DIMENSIONS},
        "diagnosis": diagnosis,
        "case_reports": all_case_reports,
    }


def format_learning_signal(report: Dict[str, Any]) -> str:
    """
    格式化学习信号为可读文本

    Args:
        report: diagnose_failures 返回的诊断报告

    Returns:
        格式化的文本报告
    """
    lines = [
        f"Scope: {report['scope']}",
        f"Source cases: {', '.join(report['source_case_ids']) or 'none'}",
        f"Diagnosis: {report['diagnosis']}",
    ]

    for dimension in DIMENSIONS:
        failures = report["dimensions"].get(dimension, [])
        lines.append(f"{dimension}: {len(failures)} failure(s)")
        lines.extend(f"- {item['case_id']}: {item['evidence']}" for item in failures)

    return "\n".join(lines)
