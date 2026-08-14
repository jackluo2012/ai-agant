"""用于实验 8-1 的真实 LLM 评估器。"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, Iterable

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from verifier import DimensionResult, FAIL, PASS, UNCERTAIN


def _json_object(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


try:
    from llm.client import get_llm_client
except ImportError:
    get_llm_client = None


class OpenAIQualityJudge:
    """评估开放性质量维度，同时引用具体的对话轮次作为证据。

    该评估器专注于两个质量维度：
    1. expression_quality: 措辞是否自然、简洁、不重复
    2. compliant_flexibility: 当请求的业务路径受阻时，是否找到不违反策略的替代方案
    """

    def __init__(self, model: str | None = None, *, evidence_client=None):
        """
        初始化 LLM 质量评估器。

        Args:
            model: 模型名称（可选，默认使用项目配置）
            evidence_client: 证据客户端（可选，默认创建新客户端）
        """
        if evidence_client is None:
            from evidence_client import EvidenceChatClient
            evidence_client = EvidenceChatClient(provider=None, model=model)
        self.client = evidence_client
        self.model = evidence_client.model

    def evaluate(self, trajectory: Dict[str, Any]) -> Iterable[DimensionResult]:
        if not isinstance(trajectory, dict):
            trajectory = {}
        facts = trajectory.get("process_facts")
        if not isinstance(facts, dict):
            facts = {}
        messages = trajectory.get("messages")
        if not isinstance(messages, list):
            messages = []
        tool_calls = trajectory.get("tool_calls")
        if not isinstance(tool_calls, list):
            tool_calls = []
        checked_rules = facts.get("checked_rules")
        if not isinstance(checked_rules, list):
            checked_rules = []
        evidence = {
            "user_request": trajectory.get("user_request"),
            "messages": messages,
            "tool_calls": tool_calls,
            "checked_rules": checked_rules,
        }
        prompt = f"""你正在校准一个客服 Agent 的轨迹。

请评估以下两个维度，并将它们的范围与代码检查层区分开：
1. expression_quality（表达质量）：仅评估措辞是否自然、简洁且不重复。不要因为事实、隐私、策略或行动错误而判定此维度失败；这些由其他层检查。向客户展示原始 JSON 不属于自然表达。
2. compliant_flexibility（合规灵活性）：如果请求的业务路径受阻，找到不违反策略的允许替代方案。用户明确提出的后备请求证明存在可用替代方案。如果没有业务路径受阻，返回通过（而非不确定），因为不需要变通方案。不要使用此维度重新评估隐私。

对每个维度，返回 verdict（pass/fail/uncertain）、0 到 1 之间的分数、0 到 1 之间的置信度，以及引用具体轮次编号的证据数组。如果记录缺乏足够证据，请使用 uncertain。仅返回 JSON：
{{"dimensions": [{{"dimension": "expression_quality", "verdict": "pass", "score": 1.0, "confidence": 0.8, "evidence": ["turn 2: ..."]}}, ...]}}

轨迹证据：
{json.dumps(evidence, ensure_ascii=False, indent=2)}
"""
        response = self.client.complete(
            kind="quality_judge",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        payload = _json_object(response.choices[0].message.content or "{}")
        if isinstance(payload, list):
            raw_dims = payload
        elif isinstance(payload, dict):
            raw_dims = payload.get("dimensions")
        else:
            raw_dims = []
        if not isinstance(raw_dims, list):
            raw_dims = []
        by_name = {
            item.get("dimension"): item
            for item in raw_dims
            if isinstance(item, dict) and item.get("dimension")
        }
        results = []
        for name in ("expression_quality", "compliant_flexibility"):
            item = by_name.get(name) or {}
            verdict = item.get("verdict", UNCERTAIN)
            if verdict not in {PASS, FAIL, UNCERTAIN}:
                verdict = UNCERTAIN
            # dict.get(key, default) returns the default only when the key is
            # ABSENT; a model that emits an explicit JSON null (common for a
            # dimension it marks "uncertain") returns None, and float(None) /
            # iterating None both raise. Coerce non-numeric / non-list values to
            # the neutral defaults instead of crashing the whole trajectory.
            score = item.get("score")
            confidence = item.get("confidence")
            evidence = item.get("evidence")
            clean_evidence = [str(v) for v in evidence if v is not None] if isinstance(evidence, list) else []
            results.append(DimensionResult(
                dimension=name,
                layer="llm_rubric",
                verdict=verdict,
                score=float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else 0.5,
                evidence=clean_evidence if clean_evidence else ["LLM returned no evidence"],
                confidence=float(confidence) if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else 0.5,
            ))
        return results
