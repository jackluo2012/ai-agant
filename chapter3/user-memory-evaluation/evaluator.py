"""基于 LLM 的代理响应评估器。"""

import json
import os
import sys
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from llm.client import get_llm_client
from config import Config
from models import (
    TestCase,
    EvaluationResult,
    RubricDimensionResult,
    RubricGrade,
    HallucinationResult,
)


DIMENSIONS = ("precision", "recall", "reasoning", "proactivity")
CORE_SUCCESS_DIMENSIONS = ("precision", "recall", "reasoning")
GRADE_BY_SCORE = {
    4: RubricGrade.EXCELLENT,
    3: RubricGrade.GOOD,
    2: RubricGrade.PASS,
    1: RubricGrade.FAIL,
}


class LLMEvaluator:
    """基于 LLM 的代理响应评估器。"""

    def __init__(self, evaluator_type: Optional[str] = None, model: Optional[str] = None):
        """
        使用指定的 LLM 初始化评估器。

        Args:
            evaluator_type: 评委后端（kimi/openai）；默认使用配置。
            model: 可选的模型名称，覆盖配置的默认值。
        """
        # 获取统一的 LLM 客户端
        self.client = get_llm_client()
        self.model = model or self.client.model_name
        self.model_lower = self.model.lower()
    
    @retry(
        stop=stop_after_attempt(Config.MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def _call_llm(self, messages: list) -> str:
        """
        调用 LLM，包含重试逻辑。

        Args:
            messages: 消息列表

        Returns:
            LLM 响应内容
        """
        # 当前推理模型拒绝任意温度设置
        if "kimi-k2.5" in self.model_lower:
            temperature = 0.6
        else:
            temperature = 1 if any(x in self.model_lower for x in ("gpt-5", "kimi-k3")) else 0
        kwargs = {}
        if "kimi-k2.5" in self.model_lower:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            timeout=Config.REQUEST_TIMEOUT,
            response_format={"type": "json_object"},
            **kwargs,
        )
        return response.choices[0].message.content
    
    def evaluate(
        self,
        test_case: TestCase,
        agent_response: str,
        extracted_memory: Optional[str] = None
    ) -> EvaluationResult:
        """
        Evaluate an agent's response against the test case criteria.
        
        Args:
            test_case: The test case being evaluated
            agent_response: The agent's response to the user question
            extracted_memory: Optional extracted memory from the agent
            
        Returns:
            EvaluationResult with detailed scoring and reasoning
        """
        evaluation_prompt = self._build_evaluation_prompt(
            test_case,
            agent_response,
            extracted_memory
        )
        
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict evidence-grounded evaluator of AI memory agents. "
                    "Score every rubric dimension independently using only the supplied "
                    "conversation source. Cite short source/answer excerpts as evidence. "
                    "Any material factual claim in the answer that is unsupported or "
                    "contradicted by the source is a hallucination. Output JSON only."
                )
            },
            {
                "role": "user",
                "content": evaluation_prompt
            }
        ]
        
        try:
            last_result = None
            for _attempt in range(Config.MAX_RETRIES):
                response = self._call_llm(messages)
                last_result = self._parse_evaluation_response(response, test_case.test_id)
                if set(last_result.dimensions) == set(DIMENSIONS) and last_result.hallucination is not None:
                    return last_result
            return last_result
        except Exception as e:
            # Return failed evaluation on error
            return EvaluationResult(
                test_id=test_case.test_id,
                reward=0.0,
                passed=False,  # For backward compatibility
                reasoning=f"Evaluation failed due to error: {str(e)}",
                required_info_found={}
            )
    
    def _build_evaluation_prompt(
        self,
        test_case: TestCase,
        agent_response: str,
        extracted_memory: Optional[str]
    ) -> str:
        """Build the evaluation prompt for the LLM."""
        histories = []
        for history in test_case.conversation_histories:
            lines = [f"[Conversation {history.conversation_id} at {history.timestamp}]"]
            lines.extend(f"{m.role.value}: {m.content}" for m in history.messages)
            histories.append("\n".join(lines))
        source = "\n\n".join(histories)

        prompt = f"""Test Case: {test_case.title}
Category: {test_case.category}
Description: {test_case.description}

AUTHORITATIVE CONVERSATION SOURCE:
{source}

User Question: {test_case.user_question}

Agent Response:
{agent_response}

"""
        if extracted_memory:
            prompt += f"""Extracted Memory (agent trace; NOT an authoritative source):
{extracted_memory}

"""
        
        prompt += f"""Evaluation Criteria:
{test_case.evaluation_criteria}
"""
        if test_case.expected_behavior:
            prompt += f"""
Expected Behavior: {test_case.expected_behavior}
"""
        prompt += """

Use this four-grade scale for EACH of the first four dimensions:
- 4 / excellent: fully meets the concrete criterion, with no material defect.
- 3 / good: meets the core criterion; only a minor non-critical omission/clarity issue.
- 2 / pass: partly meets the core criterion but has a material omission or weak linkage.
- 1 / fail: misses or contradicts the core criterion.

Dimension-specific criteria, examples, and boundaries:
1. precision: Are all stated names, numbers, dates, ownership and relationships exact?
   Excellent example: exact requested account and no confusion with a nearby savings account.
   Boundary: paraphrase is allowed; a wrong digit, date, person, or unsupported specificity is not.
2. recall: Is all information necessary for the question and evaluation criteria present?
   Excellent example: answers the direct fact and a clearly relevant setup fact requested by the criteria.
   Boundary: do not penalize omission of unrelated history; do penalize missing a required risk or qualifier.
3. reasoning: Are cross-session links, temporal updates, ownership, ambiguity and conflicts resolved correctly?
   Excellent example: links a daughter to that daughter's doctor across separate conversations.
   Boundary: if several people/items plausibly match, asking a targeted clarification is correct.
4. proactivity: Does it add useful, safe next-step help or risk warnings when appropriate?
   Excellent example: includes the remembered routing number when direct-deposit setup makes it useful.
   Boundary: concise direct answers may still be good/excellent when no additional action is useful;
   irrelevant advice or invented detail is not proactivity.
5. hallucination (VETO): mark detected=true if any material factual claim is absent from or
   contradicted by the authoritative source. A detected hallucination forces the final reward to zero.
   Boundary: general non-factual advice is allowed if clearly presented as advice, not remembered fact.
"""
        
        if test_case.category == "layer1":
            prompt += """
   - Does the agent accurately retrieve basic factual information?
   - Is the retrieved information correct and complete?"""
        elif test_case.category == "layer2":
            prompt += """
   - Does the agent properly disambiguate when faced with multiple possibilities?
   - Does it retrieve ALL relevant memory pieces, not just one?
   - Does it demonstrate contextual understanding?"""
        elif test_case.category == "layer3":
            prompt += """
   - Does the agent synthesize information across multiple conversations?
   - Does it proactively identify relevant connections?
   - Does it provide comprehensive and forward-thinking assistance?"""
        
        prompt += """

Return exactly this JSON shape (use evidence excerpts and name any applied boundary):
{
    "dimensions": {
      "precision": {"score": 1-4, "grade": "fail|pass|good|excellent", "reasoning": "...", "evidence": ["..."], "boundary_case": null},
      "recall": {"score": 1-4, "grade": "fail|pass|good|excellent", "reasoning": "...", "evidence": ["..."], "boundary_case": null},
      "reasoning": {"score": 1-4, "grade": "fail|pass|good|excellent", "reasoning": "...", "evidence": ["..."], "boundary_case": null},
      "proactivity": {"score": 1-4, "grade": "fail|pass|good|excellent", "reasoning": "...", "evidence": ["..."], "boundary_case": null}
    },
    "hallucination": {"detected": false, "claims": [], "evidence": ["..."], "reasoning": "..."},
    "overall_reasoning": "...",
    "required_info_found": {
        "concrete information item": 0.0
    },
    "suggestions": "..."
}
Do not supply an overall numeric score; the evaluator computes it from the rubric."""
        
        return prompt
    
    def _parse_evaluation_response(
        self,
        response: str,
        test_id: str
    ) -> EvaluationResult:
        """Parse the LLM's evaluation response."""
        try:
            # Extract JSON from response
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            
            data = json.loads(json_str.strip())
            
            dimensions_data = data.get("dimensions")
            if not isinstance(dimensions_data, dict):
                raise ValueError("Missing structured rubric dimensions")
            dimensions: Dict[str, RubricDimensionResult] = {}
            for name in DIMENSIONS:
                raw = dimensions_data.get(name)
                if not isinstance(raw, dict):
                    raise ValueError(f"Missing rubric dimension: {name}")
                score = int(raw["score"])
                if score not in GRADE_BY_SCORE:
                    raise ValueError(f"Invalid score for {name}: {score}")
                # The numeric grade is authoritative, preventing inconsistent model output.
                dimensions[name] = RubricDimensionResult(
                    score=score,
                    grade=GRADE_BY_SCORE[score],
                    reasoning=str(raw.get("reasoning", "")),
                    evidence=[str(v) for v in raw.get("evidence", [])],
                    boundary_case=raw.get("boundary_case"),
                )

            hallucination_raw = data.get("hallucination")
            if not isinstance(hallucination_raw, dict) or "detected" not in hallucination_raw:
                raise ValueError("Missing hallucination veto verdict")
            hallucination = HallucinationResult(
                detected=bool(hallucination_raw["detected"]),
                claims=[str(v) for v in hallucination_raw.get("claims", [])],
                evidence=[str(v) for v in hallucination_raw.get("evidence", [])],
                reasoning=str(hallucination_raw.get("reasoning", "")),
            )

            # Map 1/2/3/4 to 0, 1/3, 2/3, 1. Hallucination is a hard veto.
            reward = round(
                sum((d.score - 1) / 3 for d in dimensions.values()) / len(DIMENSIONS),
                6,
            )
            veto_applied = hallucination.detected
            if veto_applied:
                reward = 0.0

            required_info = data.get("required_info_found", {})
            if required_info and isinstance(next(iter(required_info.values()), None), bool):
                required_info = {k: 1.0 if v else 0.0 for k, v in required_info.items()}
            required_info = {str(k): max(0.0, min(1.0, float(v))) for k, v in required_info.items()}
            
            return EvaluationResult(
                test_id=test_id,
                reward=reward,
                # Task success is stricter than partial-credit reward: the answer
                # must be at least "good" on every core correctness/completeness
                # dimension. Proactivity remains diagnostic because a concise,
                # fully correct direct answer can legitimately need no extra help.
                passed=(
                    not veto_applied
                    and all(dimensions[name].score >= 3 for name in CORE_SUCCESS_DIMENSIONS)
                ),
                reasoning=data.get("overall_reasoning", "No overall reasoning provided"),
                required_info_found=required_info,
                suggestions=data.get("suggestions"),
                dimensions=dimensions,
                hallucination=hallucination,
                veto_applied=veto_applied,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            # Invalid judge output must never receive accidental partial credit.
            return EvaluationResult(
                test_id=test_id,
                reward=0.0,
                passed=False,
                reasoning=f"Evaluation response parsing failed: {str(e)}. Raw response: {response[:500]}",
                required_info_found={},
                suggestions="Consider reviewing the evaluation format"
            )


class BatchEvaluator:
    """用于运行多个测试用例的评估器。"""

    def __init__(self, evaluator_type: Optional[str] = None, model: Optional[str] = None):
        """初始化批量评估器。"""
        self.evaluator = LLMEvaluator(evaluator_type, model=model)

    def evaluate_test_suite(
        self,
        test_cases: list[TestCase],
        agent_responses: Dict[str, str],
        extracted_memories: Optional[Dict[str, str]] = None
    ) -> Dict[str, EvaluationResult]:
        """
        评估多个测试用例。

        Args:
            test_cases: 要评估的测试用例列表
            agent_responses: test_id 到代理响应的字典映射
            extracted_memories: 可选的 test_id 到提取记忆的字典映射

        Returns:
            test_id 到评估结果的字典映射
        """
        results = {}
        extracted_memories = extracted_memories or {}

        for test_case in test_cases:
            if test_case.test_id not in agent_responses:
                results[test_case.test_id] = EvaluationResult(
                    test_id=test_case.test_id,
                    reward=0.0,
                    passed=False,  # 向后兼容
                    reasoning="未为此测试用例提供代理响应",
                    required_info_found={}
                )
                continue

            result = self.evaluator.evaluate(
                test_case,
                agent_responses[test_case.test_id],
                extracted_memories.get(test_case.test_id)
            )
            results[test_case.test_id] = result

        return results

    def generate_report(
        self,
        results: Dict[str, EvaluationResult],
        test_cases: list[TestCase]
    ) -> str:
        """生成评估结果的摘要报告。"""
        report = "=" * 80 + "\n"
        report += "用户记忆评估报告\n"
        report += "=" * 80 + "\n\n"

        # 按类别分组结果
        categories = {"layer1": [], "layer2": [], "layer3": []}
        for test_case in test_cases:
            if test_case.test_id in results:
                categories[test_case.category].append(
                    (test_case, results[test_case.test_id])
                )

        # 为每个类别生成报告
        for category, items in categories.items():
            if not items:
                continue

            report += f"\n{category.upper()} - "
            if category == "layer1":
                report += "基础回忆与直接检索\n"
            elif category == "layer2":
                report += "上下文推理与消歧\n"
            elif category == "layer3":
                report += "跨会话综合与主动协助\n"
            report += "-" * 60 + "\n"

            # 结构化评分标准的通过状态已包含幻觉否决
            passed = sum(1 for _, result in items if (result.passed if result.passed is not None else result.reward >= 0.8))
            total = len(items)
            avg_reward = sum(result.reward for _, result in items) / total if total > 0 else 0

            report += f"结构化评分标准通过率：{passed}/{total} ({100*passed/total:.1f}%)\n"
            report += f"平均奖励：{avg_reward:.3f}/1.000\n\n"

            dimension_names = ("precision", "recall", "reasoning", "proactivity")
            for name in dimension_names:
                scores = [result.dimensions[name].score for _, result in items if name in result.dimensions]
                if scores:
                    report += f"平均 {name} 等级：{sum(scores) / len(scores):.2f}/4.00\n"
            vetoes = sum(bool(result.veto_applied) for _, result in items)
            report += f"幻觉否决数：{vetoes}/{total}\n\n"

            # 单个测试结果
            for test_case, result in items:
                # 根据奖励或 passed 字段确定通过/失败
                is_pass = result.passed if result.passed is not None else result.reward >= 0.8
                status = "✓ 通过" if is_pass else "✗ 失败"
                report += f"  [{status}] {test_case.title}（奖励：{result.reward:.3f}）\n"
                if result.reward < 0.8:
                    report += f"    原因：{result.reasoning}\n"

        # 总体摘要
        report += "\n" + "=" * 80 + "\n"
        report += "总体摘要\n"
        report += "=" * 80 + "\n"

        all_results = list(results.values())
        total_passed = sum(1 for r in all_results if (r.passed if r.passed is not None else r.reward >= 0.8))
        total_tests = len(all_results)
        overall_avg = sum(r.reward for r in all_results) / total_tests if total_tests > 0 else 0

        report += f"总测试数：{total_tests}\n"
        report += f"通过：{total_passed}\n"
        report += f"失败：{total_tests - total_passed}\n"
        report += f"结构化评分标准通过率：{100*total_passed/total_tests:.1f}%\n"
        report += f"平均奖励：{overall_avg:.3f}/1.000\n"
        report += f"幻觉否决数：{sum(bool(r.veto_applied) for r in all_results)}\n"

        return report
