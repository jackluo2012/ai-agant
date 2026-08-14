"""用户记忆评估框架的离线确定性指标。

``evaluator.py`` 中的 LLM 评委需要 API 密钥和网络访问。此模块提供了一个
完全离线运行的补充指标，因此基准测试可以生成跨记忆系统的评分对比，
而无需调用任何 LLM。

``KeywordRecallEvaluator`` 实现*关键事实召回*：对于每个测试用例，通过
规范化子字符串匹配检查代理响应中是否存在一组黄金事实（账户号码、
确认码、实体名称、对话历史中实际陈述的日期）。奖励等于召回的黄金事实
比例，即经典的答案包含黄金的召回指标。它与 ``LLMEvaluator`` 共享
``EvaluationResult`` 输出格式，因此两个指标在报告/对比代码中可互换使用。
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Union

from models import TestCase, EvaluationResult


# 黄金事实可以是单个必需字符串，或者是可接受的变体列表
#（其中任何一个都算作匹配，例如 ["Feb 18", "February 18"]）。
GoldFact = Union[str, List[str]]


def _normalize(text: str) -> str:
    """小写化并折叠空白字符，用于容错的子字符串匹配。"""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _fact_matched(fact: GoldFact, normalized_response: str) -> bool:
    """如果（可能是多变体的）事实出现在响应中，则返回 True。"""
    variants = fact if isinstance(fact, list) else [fact]
    return any(_normalize(v) in normalized_response for v in variants)


def _fact_label(fact: GoldFact) -> str:
    """黄金事实的可读标签（对于任一事实，使用第一个变体）。"""
    if isinstance(fact, list):
        return fact[0] + (" (…)" if len(fact) > 1 else "")
    return fact


def load_gold_facts(path: Union[str, Path]) -> Dict[str, List[GoldFact]]:
    """
    从 JSON 文件加载黄金事实标注。

    该文件将 ``test_id`` 映射到具有 ``required_facts`` 列表的对象。
    ``required_facts`` 中的每个条目是字符串或可接受的变体列表。
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    gold: Dict[str, List[GoldFact]] = {}
    for test_id, spec in data.items():
        if isinstance(spec, dict):
            gold[test_id] = spec.get("required_facts", [])
        elif isinstance(spec, list):
            gold[test_id] = spec
    return gold


class KeywordRecallEvaluator:
    """离线关键事实召回指标（无需 LLM/API）。"""

    name = "keyword-recall"

    def __init__(self, gold_facts: Dict[str, List[GoldFact]]):
        """
        Args:
            gold_facts: test_id -> 要召回的黄金事实列表的映射。
        """
        self.gold_facts = gold_facts

    def has_gold(self, test_id: str) -> bool:
        """给定测试用例是否有可用的黄金事实。"""
        return bool(self.gold_facts.get(test_id))

    def evaluate(
        self,
        test_case: TestCase,
        agent_response: str,
        extracted_memory: Optional[str] = None,
    ) -> EvaluationResult:
        """
        通过召回的黄金事实比例对响应进行评分。

        可选的 ``extracted_memory`` 与响应连接，因此代理记忆转储中
        陈述的事实也算作已召回。
        """
        facts = self.gold_facts.get(test_case.test_id, [])
        haystack = _normalize(f"{agent_response}\n{extracted_memory or ''}")

        if not facts:
            return EvaluationResult(
                test_id=test_case.test_id,
                reward=0.0,
                passed=None,
                reasoning="未定义此测试用例的黄金事实；被 keyword-recall 指标跳过。",
                required_info_found={},
            )

        info_found: Dict[str, float] = {}
        matched = 0
        for fact in facts:
            hit = _fact_matched(fact, haystack)
            info_found[_fact_label(fact)] = 1.0 if hit else 0.0
            matched += int(hit)

        recall = matched / len(facts)
        missing = [label for label, score in info_found.items() if score == 0.0]
        reasoning = f"召回 {matched}/{len(facts)} 个黄金事实。"
        if missing:
            reasoning += " 缺失：" + ", ".join(missing) + "。"

        return EvaluationResult(
            test_id=test_case.test_id,
            reward=recall,
            passed=recall >= 0.8,
            reasoning=reasoning,
            required_info_found=info_found,
        )
