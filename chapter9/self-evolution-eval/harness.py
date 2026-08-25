"""实验 8-7 的模型外部四阶段纵向评估器。"""

from __future__ import annotations

import sys
import os

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from collections import defaultdict
from typing import Any, Dict, Iterable


# 实验阶段定义
PHASES = ("learning", "transfer", "change", "retention")


def _rubric_dimension_total(rubric: dict) -> int:
    """
    向后兼容辅助函数，用于旧的结果文件和测试

    Args:
        rubric: 评分标准字典

    Returns:
        所有维度的总分
    """
    dims = ["error_handling", "input_validation", "documentation", "robustness"]
    return sum(int(value) if value is not None else 0 for value in (rubric.get(key) for key in dims))


def _rate(rows: Iterable[Dict[str, Any]], field: str) -> float:
    """
    计算指定字段为真的行数比例

    Args:
        rows: 行字典的可迭代对象
        field: 要计数的字段名

    Returns:
        指定字段为真的比例（0-1 之间）
    """
    values = [bool(row[field]) for row in rows]
    return round(sum(values) / len(values), 3) if values else 0.0


class LongitudinalEvaluator:
    """纵向实验评估器

    负责运行四个阶段的纵向评估并计算各项指标。
    """

    def run(self, agent, tasks: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        """
        运行纵向评估

        Args:
            agent: 被评估的代理实例
            tasks: 任务字典的可迭代对象

        Returns:
            包含所有评估指标的字典
        """
        records = []
        cumulative_correct = 0
        learning_seen = 0
        learning_curve = []

        for index, task in enumerate(tasks):
            if task["phase"] not in PHASES:
                raise ValueError(f"未知的实验阶段: {task['phase']}")

            # 执行代理动作
            act = agent.act(task)
            correct = act["action"] == task["expected_action"]
            safety_pass = act["action"] not in task.get("forbidden_actions", [])

            # 这是唯一的更新边界，且刻意在 act 之后
            observation = agent.observe(task)

            record = {
                "index": index,
                "task_id": task["id"],
                "phase": task["phase"],
                "rule_id": task["rule_id"],
                "expected_action": task["expected_action"],
                "actual_action": act["action"],
                "correct": correct,
                "safety_pass": safety_pass,
                "used_memory": act["used_memory"],
                "memory_available": act.get("memory_available", False),
                "memory_adherence": (
                    act["action"] == act.get("active_memory_value")
                    if act.get("memory_available") else None
                ),
                "memory_version": act["memory_version"],
                "updated_after_task": observation["updated"],
                "candidate_proposed": observation.get("candidate_proposed", False),
                "candidate_valid": observation.get("candidate_valid"),
                "event_order_valid": observation.get("event_order_valid", True),
                "tokens": act["tokens"] + observation["tokens"],
                "prompt_tokens": act.get("prompt_tokens", 0),
                "completion_tokens": act.get("completion_tokens", 0),
                "provider_reported_cost_usd": act.get("provider_reported_cost_usd"),
                "time_ms": act["time_ms"] + observation["time_ms"],
                "response_id": act.get("response_id"),
            }
            records.append(record)

            # 记录学习曲线数据
            if task["phase"] == "learning":
                learning_seen += 1
                cumulative_correct += int(correct)
                learning_curve.append({
                    "task_id": task["id"],
                    "cumulative_accuracy": round(cumulative_correct / learning_seen, 3),
                })

        # 按阶段分组
        by_phase = defaultdict(list)
        for record in records:
            by_phase[record["phase"]].append(record)

        # 计算各阶段准确率
        phase_accuracy = {phase: _rate(by_phase[phase], "correct") for phase in PHASES}

        # 变更阶段分析
        change_rows = by_phase["change"]
        # C1 仅在其动作后携带新信号。恢复测量在后续任务上进行，
        # 因此 C2 正确意味着在信号后的一个任务。
        first_recovered = next((i for i, row in enumerate(change_rows[1:], 1) if row["correct"]), None)

        # 负迁移分析
        negative_candidates = [
            row for row in records
            if row["phase"] in {"transfer", "change", "retention"} and row["used_memory"]
        ]
        negative_transfer_rate = (
            round(sum(not row["correct"] for row in negative_candidates) / len(negative_candidates), 3)
            if negative_candidates else 0.0
        )

        # 保留阶段分析
        unchanged_retention = [row for row in by_phase["retention"] if row["rule_id"] != "baggage.economy_allowance"]
        current_rule_retention = [row for row in by_phase["retention"] if row["rule_id"] == "baggage.economy_allowance"]

        # 替换分析
        replacement_rows = change_rows[1:] + current_rule_retention
        proposed = [row for row in records if row["candidate_proposed"]]
        activated = [row for row in records if row["phase"] != "learning" and row["memory_available"]]
        adherence = [row for row in records if row["memory_adherence"] is not None]
        native_costs = [row["provider_reported_cost_usd"] for row in records if row["provider_reported_cost_usd"] is not None]

        return {
            "profile": agent.profile,
            "phase_accuracy": phase_accuracy,
            "learning_curve": learning_curve,
            "transfer_accuracy": phase_accuracy["transfer"],
            "retention_rate": phase_accuracy["retention"],
            "old_capability_retention_rate": _rate(unchanged_retention, "correct"),
            "current_rule_retention_rate": _rate(current_rule_retention, "correct"),
            "adaptation": {
                "recovered": first_recovered is not None,
                "tasks_after_change_signal_to_recover": first_recovered,
                "recovery_score": 1 / (1 + first_recovered) if first_recovered is not None else 0.0,
                "change_phase_accuracy": phase_accuracy["change"],
            },
            "replacement": {
                "rule_replacement_accuracy": _rate(replacement_rows, "correct"),
                "obsolete_rule_reference_rate": round(
                    sum(row["actual_action"] == "answer_20kg" for row in replacement_rows) / len(replacement_rows), 3
                ) if replacement_rows else 0.0,
            },
            "negative_transfer_rate": negative_transfer_rate,
            "safety_rubric_pass_rate": _rate(records, "safety_pass"),
            "post_learning_safety_pass_rate": _rate(
                [row for row in records if row["phase"] != "learning"], "safety_pass"
            ),
            "update_metrics": {
                "candidate_modification_validity": _rate(proposed, "candidate_valid") if proposed else None,
                "artifact_activation_rate": _rate(activated, "used_memory") if activated else None,
                "memory_adherence_rate": _rate(adherence, "memory_adherence") if adherence else None,
            },
            "feedback_order_valid": all(row["event_order_valid"] for row in records),
            "cost": {
                "tokens": sum(row["tokens"] for row in records),
                "prompt_tokens": sum(row["prompt_tokens"] for row in records),
                "completion_tokens": sum(row["completion_tokens"] for row in records),
                "time_ms": sum(row["time_ms"] for row in records),
                "storage_bytes": agent.storage_bytes,
                "provider_reported_cost_usd": round(sum(native_costs), 9) if native_costs else None,
                "cost_qualification": (
                    "提供商原生 usage.cost 的总和" if native_costs
                    else "提供商未公开货币成本；未猜测价格"
                ),
            },
            "records": records,
        }
