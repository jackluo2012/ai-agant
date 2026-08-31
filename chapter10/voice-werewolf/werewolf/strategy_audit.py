# -*- coding: utf-8 -*-
"""赛后基于证据的角色策略验收审计。

对局结束后，把完整的行为历史交给 LLM 评审员，按四条标准逐项打分
（仅引用日志中真实存在的行动作为证据，禁止臆造未记录的行为）。本模块
fail-closed：任何格式不合规的模型输出都会被判定为验收失败，而不是被
误当成通过。
"""

from __future__ import annotations

import json
import os
import sys

# 添加项目根目录到路径（用于导入统一的 llm.client 模块）
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from llm.client import get_llm_client
except ImportError:
    get_llm_client = None


# 四条必须逐项评审的验收标准（键名保持英文以便机器校验）
REQUIRED_CRITERIA = (
    "werewolf_concealment",
    "seer_timing_and_evidence",
    "villager_logical_reasoning",
    "role_consistency",
)
VALID_STATUSES = {"pass", "fail", "insufficient"}


def validate_strategy_result(result):
    """把模型评分转化为严格、可机器校验的验收记录。

    本函数刻意 fail-closed。提供商 SDK 偶尔会在 JSON 模式响应被截断时返回
    ``None`` 或标量；若直接对其修改会抛出偶发的 ``AttributeError`` 并中断
    报告生成。返回一个正常的、可序列化的拒绝结果，可以让验收流程保持可
    审计，并防止格式不合规的模型输出被误认为通过。
    """
    errors = []
    if not isinstance(result, dict):
        return {
            "model_overall_pass_claim": None,
            "schema_valid": False,
            "validation_errors": ["策略评审结果必须是 JSON 对象"],
            "overall_pass": False,
        }
    criteria = result.get("criteria")
    if not isinstance(criteria, dict):
        criteria = {}
        errors.append("criteria 必须是对象")
    for name in REQUIRED_CRITERIA:
        item = criteria.get(name)
        if not isinstance(item, dict):
            errors.append(f"缺少评审项对象：{name}")
            continue
        status = item.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"{name} 的 status 非法：{status!r}")
        evidence = item.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            errors.append(f"{name} 缺少引用证据：{name}")
    claimed = result.get("overall_pass")
    # 计算真实通过状态：所有评审项齐全且全部 pass 才算通过
    computed_pass = not errors and all(
        criteria[name].get("status") == "pass" for name in REQUIRED_CRITERIA
    )
    result["model_overall_pass_claim"] = claimed
    result["schema_valid"] = not errors
    result["validation_errors"] = errors
    result["overall_pass"] = computed_pass
    return result


def strategy_acceptance_passes(result):
    """返回策略验收是否整体通过（schema 合法 且 各项均为 pass）。"""
    return bool(
        isinstance(result, dict)
        and result.get("schema_valid") is True
        and result.get("overall_pass") is True
    )


def evaluate_strategy(judge):
    """调用统一 LLM 客户端对整局行为做策略验收评审，返回结构化评审结果。"""
    if get_llm_client is None:
        raise RuntimeError(
            "无法导入统一 LLM 客户端 llm.client，策略审计不可用。"
            "请从项目根目录运行本实验。"
        )
    # 组装评审载荷：角色表 + 完整行动历史 + 四条标准说明（发给 LLM 的提示词用中文）
    roles = {p.name: p.role.value for p in judge.players}
    payload = {
        "roles": roles,
        "actions": judge.action_history,
        "criteria": {
            "werewolf_concealment": "狼人的公开发言合理地隐藏了身份，且没有暴露队友。",
            "seer_timing_and_evidence": "预言家在合适的时机公布查验结果，且只报告自己真实已知的结果。",
            "villager_logical_reasoning": "村民的怀疑引用了公开发言或投票行为，而不是随机猜测。",
            "role_consistency": "AI 的行动与公开发言符合角色能力与目标。",
        },
        "instruction": (
            "仅使用 pass/fail/insufficient 三种状态给每条标准评分，并附上简短、"
            "引自行动记录的证据。不得推断日志中不存在的行为。返回且仅返回一个 "
            "JSON 对象，形如 {\"criteria\": {\"werewolf_concealment\": "
            "{\"status\": \"pass|fail|insufficient\", \"evidence\": \"引用\"}, "
            "\"seer_timing_and_evidence\": {...}, \"villager_logical_reasoning\": "
            "{...}, \"role_consistency\": {...}}, \"overall_pass\": true|false}。"
            "字段名必须用 status（不要用 grade），并包含全部四条命名的评审项。"
        ),
    }
    client = get_llm_client()
    kwargs = dict(
        model=client.model_name,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        response_format={"type": "json_object"},
    )
    # 兼容不支持自定义 temperature 的模型：kimi 系列要求 temperature=1
    if "kimi" in (client.model_name or "").lower():
        kwargs.update(temperature=1, max_tokens=4096)
    response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content or "{}"
    raw_result = json.loads(content)
    # validate_strategy_result 会原地标注输入。这里保留一份不含凭证的原始
    # 结果放进尝试记录，避免把尝试记录挂到已验收结果上时形成自引用的 JSON。
    result = json.loads(content)
    result["model"] = client.model_name
    checked = validate_strategy_result(result)
    usage = getattr(response, "usage", None)
    usage = usage.model_dump() if hasattr(usage, "model_dump") else usage
    attempt = {
        "model": client.model_name,
        "response_id": getattr(response, "id", None),
        "provider_reported_model": getattr(response, "model", None),
        "usage": usage,
        "schema_valid": checked["schema_valid"],
        "validation_errors": checked["validation_errors"],
        "raw_result": raw_result,
    }
    if checked["schema_valid"]:
        checked["judge_attempts"] = [attempt]
        return checked
    failure = RuntimeError(
        "策略验收评审返回了不合规的结构："
        + "; ".join(checked["validation_errors"])
    )
    failure.judge_attempts = [attempt]
    raise failure
