"""
本地配置模块：处理 API 调用跟踪和使用统计。

底层 LLM 客户端使用项目统一的 llm.client 模块。

功能说明：
    - 提供 API 调用记录功能（用于分析成本和性能）
    - 统一管理 LLM 提供商和模型配置
    - 处理 temperature 等参数配置
"""

import os
import time
from typing import Any

# 添加项目根目录到路径
import sys
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from llm.client import get_llm_client

# API 调用跟踪列表
API_TURNS = []


def get_provider() -> str:
    """
    获取当前配置的 LLM 提供商

    Returns:
        提供商名称（如 openai, kimi, deepseek 等）
    """
    client = get_llm_client()
    # 从环境变量或客户端配置获取提供商
    return os.getenv("LLM_PROVIDER", "openai")


def get_model() -> str:
    """
    获取当前配置的模型名称

    Returns:
        模型名称（如 kimi-k3, gpt-4o 等）
    """
    client = get_llm_client()
    return client.model_name


def get_client():
    """
    获取统一的 LLM 客户端

    Returns:
        LLM 客户端实例
    """
    return get_llm_client()


def get_temperature() -> float:
    """
    获取当前配置的 temperature 参数

    推理模型（gpt-5.x / o 系列 / kimi-k3 等）使用默认 temperature=1，
    其他模型使用 temperature=0 以保证可复现性。

    Returns:
        temperature 值（0.0 或 1.0）
    """
    # 推理模型使用默认 temperature=1，其他使用 0
    model = get_model()
    if model.startswith(("gpt-5", "o1", "o3", "o4")) or "kimi-k3" in model.lower():
        return 1.0
    return float(os.getenv("LLM_TEMPERATURE", "0"))


def _jsonable(value: Any) -> Any:
    """
    将值转换为可 JSON 序列化的形式

    Args:
        value: 待转换的值

    Returns:
        可 JSON 序列化的值
    """
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def record_completion(*, kind: str, **request: Any) -> Any:
    """
    执行 LLM 调用并记录请求/响应（不包含凭证）

    Args:
        kind: 调用类型标识（如 "task_agent", "llm_judge", "coding_agent"）
        **request: 传递给 LLM 客户端的请求参数

    Returns:
        LLM 响应对象
    """
    client = get_client()
    started = time.time()

    # 执行实际的 LLM 调用
    response = client.chat.completions.create(**request)

    # 记录调用信息（不包含凭证）
    API_TURNS.append({
        "kind": kind,
        "provider": get_provider(),
        "model": get_model(),
        "request": _jsonable(request),
        "response": _jsonable(response.model_dump(mode="json", exclude_none=True)),
        "elapsed_seconds": round(time.time() - started, 6),
    })

    return response


def reset_api_turns() -> None:
    """清空 API 调用记录"""
    API_TURNS.clear()


def get_api_turns() -> list[dict]:
    """
    获取所有 API 调用记录

    Returns:
        API 调用记录列表
    """
    return list(API_TURNS)


def get_backend_metadata() -> dict[str, Any]:
    """
    获取后端元数据信息

    Returns:
        包含提供商、模型、端点等信息的字典
    """
    provider = get_provider()
    client = get_client()
    base_url = getattr(client, "base_url", None) or "https://api.openai.com/v1"

    return {
        "configured_provider": provider,
        "model": get_model(),
        "endpoint": f"{base_url}/chat/completions",
        "credential_source_env": f"{provider.upper()}_API_KEY",
        "credential_value_recorded": False,
    }


def usage_summary() -> dict[str, Any]:
    """
    统计 token 使用量和成本信息

    Returns:
        包含 prompt_tokens、completion_tokens、total_tokens 和成本信息的字典
    """
    prompt = completion = total = 0
    native_cost = 0.0
    native_cost_count = 0

    for turn in API_TURNS:
        usage = turn.get("response", {}).get("usage") or {}
        prompt += int(usage.get("prompt_tokens") or 0)
        completion += int(usage.get("completion_tokens") or 0)
        total += int(usage.get("total_tokens") or 0)
        if usage.get("cost") is not None:
            native_cost += float(usage["cost"])
            native_cost_count += 1

    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total or prompt + completion,
        "provider_reported_cost_usd": round(native_cost, 9) if native_cost_count else None,
        "provider_reported_cost_observations": native_cost_count,
        "cost_qualification": (
            "provider-native usage.cost summed across calls"
            if native_cost_count else "provider did not expose monetary cost; no price was guessed"
        ),
    }
