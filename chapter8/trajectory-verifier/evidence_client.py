"""无凭据的真实对话补全捕获器，用于实验 8-1。"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from llm.client import get_llm_client
except ImportError:
    # 如果无法导入统一客户端，回退到直接使用 OpenAI
    from openai import OpenAI as DirectOpenAI
    get_llm_client = None


def _dump(value: Any) -> Any:
    """递归清理对象为可序列化的字典。"""
    if hasattr(value, "model_dump"):
        return _dump(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, dict):
        return {str(key): _dump(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_dump(item) for item in value]
    return value


class EvidenceChatClient:
    """记录请求和响应的 OpenAI 兼容客户端，永不记录凭据。

    该客户端包装统一的 LLM 客户端，用于实验 8-1 中记录 API 调用详情。
    """

    def __init__(self, provider: str | None = None, model: str | None = None):
        """
        初始化证据客户端。

        Args:
            provider: 提供商名称（可选，默认使用项目配置）
            model: 模型名称（可选，默认使用项目配置）
        """
        if get_llm_client is None:
            # 回退模式：直接使用 OpenAI
            raise RuntimeError("无法导入统一 LLM 客户端，请确保 llm 模块可用")

        # 获取统一客户端
        self.client = get_llm_client()
        self.model = model or self.client.model_name
        self.provider = provider or getattr(self.client, 'provider', 'default')
        self.base_url = getattr(self.client, 'base_url', 'N/A')
        self.credential_source_env = "LLM_CLIENT"  # 使用统一客户端
        self.api_turns: list[dict[str, Any]] = []

    def complete(self, *, kind: str, **kwargs: Any) -> Any:
        """
        完成对话调用并记录详情。

        Args:
            kind: 调用类型标识（如 "customer_service_agent", "quality_judge"）
            **kwargs: 传递给 LLM 客户端的其他参数

        Returns:
            LLM 响应对象
        """
        # 确保使用正确的模型
        request = {"model": self.model, **kwargs}
        started = time.time()
        response = self.client.chat.completions.create(**request)
        elapsed = time.time() - started

        # 记录调用详情
        self.api_turns.append({
            "kind": kind,
            "endpoint": f"{self.base_url}/chat/completions",
            "provider": self.provider,
            "request": _dump(request),
            "response": _dump(response),
            "elapsed_seconds": round(elapsed, 6),
        })
        return response

    def usage_summary(self) -> dict[str, Any]:
        """
        汇总所有 API 调用的使用情况。

        Returns:
            包含令牌计数和成本信息的字典
        """
        prompt = completion = total = 0
        native_cost = 0.0
        cost_observations = 0
        for turn in self.api_turns:
            usage = turn.get("response", {}).get("usage") or {}
            prompt += int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            completion += int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            total += int(usage.get("total_tokens") or 0)
            if usage.get("cost") is not None:
                native_cost += float(usage["cost"])
                cost_observations += 1
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total or prompt + completion,
            "provider_reported_cost_usd": round(native_cost, 9) if cost_observations else None,
            "provider_reported_cost_observations": cost_observations,
            "cost_qualification": (
                "provider-native usage.cost summed across all calls"
                if cost_observations
                else "provider did not expose monetary cost; no price was guessed"
            ),
        }
