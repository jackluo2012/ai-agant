"""
智能处理工具：代码生成、推理和验证。
基于 AWorld intelligence-* 服务器。
"""
import json
import logging
import os
import sys
from typing import Dict, Any, List

from openai import OpenAI
from dotenv import load_dotenv

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from llm_fallback import resolve_llm


load_dotenv()
logger = logging.getLogger(__name__)


def _client_and_model():
    """构建 OpenAI 兼容的客户端和模型，支持 OpenRouter 回退

    当存在 OPENAI_API_KEY 时直接使用；否则路由到 OPENROUTER_API_KEY。
    当两者都未配置时抛出 RuntimeError（列出可接受的密钥），以便调用者
    能够显示清晰的错误信息。

    Returns:
        tuple: (OpenAI 客户端实例, 模型名称)
    """
    # 解析 LLM 配置（API 密钥、基础 URL、模型名称）
    api_key, base_url, model = resolve_llm()
    # 创建客户端：如果有 base_url 则使用，否则使用默认
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    return client, model


async def generate_python_code(
    task_description: str,
    requirements: str | None = None,
    temperature: float = 0.7
) -> Dict[str, Any]:
    """
    根据任务描述生成 Python 代码

    Args:
        task_description: 代码应完成的功能描述
        requirements: 可选的额外要求
        temperature: LLM 温度参数（控制创造性）

    Returns:
        包含生成代码的字典
    """
    try:
        try:
            client, model = _client_and_model()
        except RuntimeError as e:
            return {"success": False, "error": str(e)}

        prompt = f"""为以下任务生成 Python 代码：

任务：{task_description}

{f'要求：{requirements}' if requirements else ''}

请提供清晰、有良好文档的 Python 代码来解决该任务。"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一位专业的 Python 程序员。生成清晰、高效的代码。"},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=2000
        )

        # 提取生成的代码
        code = response.choices[0].message.content

        return {
            "success": True,
            "task": task_description,
            "code": code,
            "model": model,
            "tokens_used": response.usage.total_tokens if response.usage else 0
        }

    except Exception as e:
        return {"success": False, "error": f"代码生成失败：{str(e)}"}


async def complex_problem_reasoning(
    problem: str,
    context: str | None = None,
    reasoning_steps: int = 3
) -> Dict[str, Any]:
    """
    执行复杂问题推理，采用逐步思考方式

    Args:
        problem: 问题描述
        context: 可选的上下文信息
        reasoning_steps: 推理步骤数量

    Returns:
        包含推理过程和结论的字典
    """
    try:
        try:
            client, model = _client_and_model()
        except RuntimeError as e:
            return {"success": False, "error": str(e)}

        prompt = f"""用逐步推理的方式分析以下问题：

问题：{problem}

{f'上下文：{context}' if context else ''}

请一步步思考这个问题。请提供 {reasoning_steps} 个清晰的推理步骤，然后给出你的结论。"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一位专业的问题解决专家。请逐步思考。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1500
        )

        # 提取推理结果
        reasoning = response.choices[0].message.content

        return {
            "success": True,
            "problem": problem,
            "reasoning": reasoning,
            "model": model,
            "tokens_used": response.usage.total_tokens if response.usage else 0
        }

    except Exception as e:
        return {"success": False, "error": f"推理失败：{str(e)}"}


async def guard_reasoning_process(
    proposed_action: str,
    context: Dict[str, Any],
    safety_rules: List[str] | None = None
) -> Dict[str, Any]:
    """
    验证和评估拟议的操作或推理过程

    Args:
        proposed_action: 拟议执行的操作
        context: 用于评估的上下文信息
        safety_rules: 可选的安全规则列表

    Returns:
        包含安全评估的字典
    """
    try:
        try:
            client, model = _client_and_model()
        except RuntimeError as e:
            return {"success": False, "error": str(e)}

        rules_text = "\n".join(f"- {rule}" for rule in (safety_rules or []))
        safety_rules_block = f"安全规则检查：\n{rules_text}" if safety_rules else ""

        prompt = f"""评估以下拟议操作的安全性和适当性：

拟议操作：{proposed_action}

上下文：{json.dumps(context, indent=2, ensure_ascii=False)}

{safety_rules_block}

请分析该操作是否符合以下标准：
1. 执行安全
2. 与上下文和目标一致
3. 无潜在有害后果

请提供：
- approved: true/false
- reasoning: 你的评估理由
- concerns: 任何安全顾虑（没有则为空）
- suggestions: 如不批准，提供替代方案"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一位安全验证专家。请仔细评估拟议的操作。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800
        )

        # 获取评估结果
        evaluation = response.choices[0].message.content

        # 尝试提取结构化响应。批准必须是明确的且不被否定：
        # 仅用"safe to execute"作为信号是不可用的，因为它是
        # "not safe to execute"的子串（并且提示词本身也包含该短语），
        # 这会将拒绝反转为批准。当裁决不明确时，默认为不批准。
        low = evaluation.lower()
        approved = (
            "approved: true" in low
            and "approved: false" not in low
            and "not safe" not in low
            and "unsafe" not in low
        )

        return {
            "success": True,
            "proposed_action": proposed_action,
            "approved": approved,
            "evaluation": evaluation,
            "model": model
        }

    except Exception as e:
        return {"success": False, "error": f"验证失败：{str(e)}"}
