"""实验 8-5 中使用的真实 API 编码代理。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Dict

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
    get_llm_client = None

from evolution import candidate_from_source


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _client(provider: str, model: str | None = None) -> tuple[Any, dict[str, Any]]:
    """
    获取 LLM 客户端

    Args:
        provider: 提供商名称（已弃用，保留兼容性）
        model: 模型名称（可选）

    Returns:
        (客户端实例, 后端信息字典)
    """
    if get_llm_client is None:
        raise RuntimeError("LLM 客户端模块未正确导入")

    client = get_llm_client()
    base = getattr(client, 'base_url', '默认端点')
    return client, {
        "provider": provider or "default",
        "endpoint": base + "/chat/completions" if base else "默认/chat/completions",
        "credential_env": "API_KEY"
    }


def generate_with_openai(
    stable_source: str,
    diagnosis: Dict[str, Any],
    model: str | None = None,
    *,
    provider: str = "openrouter",
    seed: int = 8501,
    rejected_history: list[dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    使用 LLM 生成候选代码

    Args:
        stable_source: 稳定版本的源代码
        diagnosis: 失败诊断信息
        model: 模型名称（可选）
        provider: 提供商名称（已弃用，保留兼容性）
        seed: 随机种子
        rejected_history: 之前被拒绝的候选历史

    Returns:
        候选代码和元数据字典
    """
    client, backend = _client(provider, model)
    selected_model = model or client.model_name

    prompt = f"""你是一个受控自我修改流水线中的编码代理。

仅修改提供的重试策略模块。保留公共函数签名和临时故障的重试行为。
永久故障（retryable=false 或列出的永久代码）不得重试，必须在首次出现时打开熔断器。
将 VERSION 更新为候选版本。不得导入模块、访问文件或修改验证/发布逻辑。

在源代码之前，预测预期影响。仅返回 JSON：
{{"impact_prediction": {{"non_retryable_calls": {{"before": "最多 4 次", "after": 1}},
"temporary_timeout_recovery_rate": {{"before": 1.0, "after": 1.0}}}},
"source": "完整的 Python 模块"}}

失败诊断：
{json.dumps(diagnosis, ensure_ascii=False, indent=2)}

之前被拒绝的候选（不要重复它们的失败）：
{json.dumps(rejected_history or [], ensure_ascii=False, indent=2)}

稳定模块：
{stable_source}
"""
    request = {
        "model": selected_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "seed": seed,
        "max_tokens": 1400,
        "response_format": {"type": "json_object"},
    }
    started = time.perf_counter()
    response = client.chat.completions.create(**request)
    elapsed = time.perf_counter() - started
    raw = response.model_dump(mode="json", exclude_none=True)
    payload = _extract_json(response.choices[0].message.content or "")
    source = str(payload.get("source", ""))
    if not source.endswith("\n"):
        source += "\n"
    usage = raw.get("usage") or {}
    cost = usage.get("cost")
    receipt = {
        "backend": {**backend, "model": selected_model, "credential_value_recorded": False},
        "request": request,
        "response": raw,
        "request_sha256": hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest(),
        "response_sha256": hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest(),
        "elapsed_seconds": round(elapsed, 6),
        "usage": {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "provider_reported_cost_usd": float(cost) if cost is not None else None,
            "cost_qualification": (
                "provider-native usage.cost" if cost is not None
                else "provider did not expose monetary cost; no price was guessed"
            ),
        },
    }
    return candidate_from_source(
        stable_source,
        source,
        impact_prediction=payload.get("impact_prediction") or {},
        generator_metadata={
            "generator": "real_llm_coding_agent", "model": selected_model,
            "provider": provider, "seed": seed, "api_calls": 1, "receipt": receipt,
        },
    )
