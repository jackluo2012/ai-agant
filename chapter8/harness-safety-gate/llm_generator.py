"""实验 8-8 的真实 Coding Agent 路径（使用统一 LLM 客户端）。

读取失败诊断与稳定版调度器源码，让模型产出候选 confirmation_gate.py。
输出只能写入 validation/<run>/candidates/ 隔离目录；静态检查、回放验证、
发布决定全部由模型外部代码做出。原始请求/响应与用量保存在证据回执中。
"""

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

from evolution import candidate_from_gate


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _get_backend_info(provider: str) -> dict[str, Any]:
    """
    获取后端信息（用于证据回执）。

    Args:
        provider: 提供商标识

    Returns:
        包含提供商信息的字典
    """
    client = get_llm_client()
    backend = {
        "provider": provider,
        "endpoint": f"{client.base_url}chat/completions" if hasattr(client, 'base_url') else "unknown",
        "credential_env": "API_KEY",
    }
    return backend


PROMPT_TEMPLATE = """你是一个受控的 Harness 演化流水线中的 Coding Agent。

失败信号（用户纠正、点踩、事后审计）显示，稳定版工具调度器在未经用户确认的情况下执行了不可逆的高风险调用。请编写一个新的 Python 模块 confirmation_gate.py，在调度前添加确认门禁。不要修改稳定版模块；harness 会接入你的模块。不要修改验证/发布逻辑。

该模块必须定义以下可调用对象：
- requires_confirmation(tool_name, args=None) -> bool
- issue_confirmation(tool_name, args=None) -> str
  （一个一次性令牌，绑定到确切的工具名和完整参数）
- dispatch(tool_name, args=None, *, execute, confirm_token=None) -> dict

dispatch 行为契约（execute 由 harness 注入；永远不要自己调用真实工具）：
- 低风险调用：返回 {{"status": "executed", "confirmed": false, "result": execute(tool_name, args)}}
- 无令牌的高风险调用：返回 {{"status": "pending_confirmation", "reason": ...}} 并且永远不要调用 execute
- 持有针对此工具+参数的有效未使用令牌的高风险调用：消费该令牌，然后返回 {{"status": "executed", "confirmed": true, "result": execute(tool_name, args)}}
- 无效、已使用或不匹配的令牌：返回 {{"status": "rejected", "reason": ...}} 并且永远不要调用 execute

高风险规则（工具名 + 参数模式）：
- delete_file（任何路径）
- 带有 force=true 的 git_push
- 包含 DROP TABLE / TRUNCATE 或无 WHERE 的 DELETE ... 的 sql_query
- 带有破坏性模式（rm -rf, mkfs, shutdown, dd if=）的 run_shell
其他所有操作都是低风险，绝不能被挂起。

只能从以下模块导入：hashlib, hmac, json, re, secrets, string。没有文件、网络或子进程访问。设置 VERSION = "1.1.0-candidate"。

在源代码之前，预测预期影响。仅返回 JSON：
{{"impact_prediction": {{"unconfirmed_high_risk_executions": {{"after": 0}},
"low_risk_calls_suspended": {{"after": 0}}}},
"source": "完整的 Python 模块"}}

失败诊断：
{diagnosis}

先前被拒绝的候选（不要重复它们的失败）：
{rejected_history}

稳定版模块（只读上下文；不要修改）：
{stable_source}
"""


def generate_with_openai(
    stable_source: str,
    diagnosis: Dict[str, Any],
    model: str | None = None,
    *,
    provider: str = "default",
    seed: int = 8801,
    rejected_history: list[dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    使用统一 LLM 客户端生成候选确认门禁代码。

    Args:
        stable_source: 稳定版调度器源代码
        diagnosis: 失败诊断信息
        model: 模型名称（可选，默认使用 .env 配置）
        provider: 提供商标识（已弃用，保留用于向后兼容）
        seed: 随机种子
        rejected_history: 之前被拒绝的候选列表

    Returns:
        包含候选代码和元数据的字典
    """
    if get_llm_client is None:
        raise RuntimeError("无法导入 LLM 客户端，请确保项目根目录配置正确")

    # 获取统一客户端
    client = get_llm_client()
    backend = _get_backend_info(provider)
    selected_model = model or client.model_name

    # 构建提示词
    prompt = PROMPT_TEMPLATE.format(
        diagnosis=json.dumps(diagnosis, ensure_ascii=False, indent=2),
        rejected_history=json.dumps(rejected_history or [], ensure_ascii=False, indent=2),
        stable_source=stable_source,
    )

    # 构建请求
    request = {
        "model": selected_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "seed": seed,
        "max_tokens": 2400,
        "response_format": {"type": "json_object"},
    }

    # 发起请求并计时
    started = time.perf_counter()
    response = client.chat.completions.create(**request)
    elapsed = time.perf_counter() - started

    # 处理响应
    raw = response.model_dump(mode="json", exclude_none=True)
    payload = _extract_json(response.choices[0].message.content or "")
    source = str(payload.get("source", ""))
    if not source.endswith("\n"):
        source += "\n"

    # 提取用量信息
    usage = raw.get("usage") or {}
    cost = usage.get("cost")

    # 构建证据回执
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
                "提供商原生用量成本" if cost is not None
                else "提供商未暴露货币成本；未猜测价格"
            ),
        },
    }

    # 返回候选对象
    return candidate_from_gate(
        source,
        impact_prediction=payload.get("impact_prediction") or {},
        generator_metadata={
            "generator": "real_llm_coding_agent", "model": selected_model,
            "provider": provider, "seed": seed, "api_calls": 1, "receipt": receipt,
        },
    )
