"""LLM 决策点：让 Computer Use Agent 自主决定是否调用 ``initiate_phone_call_agent``。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from models import DecisionRecord, FieldSpec

# 添加项目根目录到路径，以便导入统一 LLM 客户端
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

TOOL_NAME = "initiate_phone_call_agent"


def _build_client():
    """获取统一 LLM 客户端（自动读取项目根目录 .env 配置）。"""
    if get_llm_client is None:
        raise RuntimeError(
            "无法导入统一 LLM 客户端 llm.client。"
            "请在项目根目录 ai-agant 下运行（需包含 llm/ 目录）。"
        )
    return get_llm_client()


async def decide_orchestration(
    *,
    page_url: str,
    page_title: str,
    fields: list[FieldSpec],
    known_values: dict[str, str],
    elapsed: float,
    raw_request_path: str | None = None,
    raw_response_path: str | None = None,
) -> DecisionRecord:
    """让 Computer Use Agent 自主选择是否启动 Phone Agent。

    代码里刻意不写 ``if len(fields)`` 这样的 Python 规则。模型看到的是
    浏览器观察、已有上下文和一个可选工具；``tool_choice=auto`` 就是本实验
    的自主性边界。
    """

    if bool(raw_request_path) != bool(raw_response_path):
        raise ValueError("raw_decision_request 与 raw_decision_response 必须同时提供")
    client = _build_client()
    model = client.model_name
    provider = client.provider
    visible_fields = [
        {
            "name": f.name,
            "label": f.label,
            "type": f.input_type,
            "required": f.required,
            "format_hint": f.format_hint,
            "options": f.options,
        }
        for f in fields
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": TOOL_NAME,
                "description": (
                    "当用户需要通过对话提供大量缺失的结构化信息时，启动一个实时 Phone Agent。"
                    "Phone Agent 会逐项提问、确认、校验格式，并把收集到的每个字段实时回传给"
                    "浏览器 Agent。仅缺失一两个简单值时不要调用它。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "purpose": {"type": "string"},
                        "required_info": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "label": {"type": "string"},
                                    "format_hint": {"type": "string"},
                                },
                                "required": ["name", "label"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["purpose", "required_info"],
                    "additionalProperties": False,
                },
            },
        }
    ]
    kwargs = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个正在完成注册任务的 Computer Use Agent。请检查真实页面观察结果"
                    "和上下文中已有的信息。当你需要收集大量结构化信息、且可以通过对话逐项"
                    "完成时，考虑调用 Phone Agent 工具。缺失一两个简单值时不要调用。"
                    "绝不编造用户数据。只给出简短的决策摘要，不要泄露私有思维链。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request": "帮我在这个网站上完成注册",
                        "page_url": page_url,
                        "page_title": page_title,
                        "form_fields": visible_fields,
                        "known_context_fields": sorted(known_values),
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "tools": tools,
        "tool_choice": "auto",
    }
    # 统一客户端是同步实现，放到线程池中执行，避免阻塞事件循环
    request_started = time.monotonic()
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create, model=model, **kwargs
        )
    except Exception as exc:
        raise RuntimeError(
            f"文本模型端点调用失败（provider={provider}，model={model}）：{type(exc).__name__}"
        ) from exc
    provider_latency_seconds = round(time.monotonic() - request_started, 6)
    if raw_request_path and raw_response_path:
        # 留痕凭据不含任何 API 凭据字段
        request_receipt = {
            "schema_version": 1,
            "experiment": "10-3",
            "provider": provider,
            "endpoint": str(client.base_url).rstrip("/"),
            "credential_fields_retained": [],
            "request": {"model": model, **kwargs},
        }
        response_receipt = {
            "schema_version": 1,
            "experiment": "10-3",
            "provider": provider,
            "latency_seconds": provider_latency_seconds,
            "response": response.model_dump(mode="json"),
        }
        for path_value, receipt in (
            (raw_request_path, request_receipt),
            (raw_response_path, response_receipt),
        ):
            path = Path(path_value)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    message = response.choices[0].message
    call = next((c for c in (message.tool_calls or []) if c.function.name == TOOL_NAME), None)
    purpose = ""
    requested: list[FieldSpec] = []
    if call:
        args = json.loads(call.function.arguments)
        purpose = str(args.get("purpose", ""))
        # 把模型给出的字段映射回页面上真实存在的字段（按 name 或 label 匹配）
        by_name = {f.name: f for f in fields}
        by_label = {f.label.casefold(): f for f in fields}
        for item in args.get("required_info", []):
            candidate = by_name.get(str(item.get("name", ""))) or by_label.get(
                str(item.get("label", "")).casefold()
            )
            # 上下文已有的字段不重复收集；同一字段不重复出现
            if candidate and candidate.name not in known_values and candidate not in requested:
                requested.append(candidate)

    return DecisionRecord(
        page_url=page_url,
        page_title=page_title,
        known_fields=sorted(known_values),
        discovered_fields=fields,
        tool_called=TOOL_NAME if call else None,
        purpose=purpose,
        required_info=requested,
        rationale_summary=(
            message.content or "模型通过工具调用决定启动 Phone Agent"
            if call
            else "模型决定继续当前流程"
        ).strip(),
        model=model,
        monotonic_seconds=round(time.monotonic() - elapsed, 6),
        provider=provider,
        provider_response_id=getattr(response, "id", None),
        provider_usage={
            key: int(value)
            for key, value in {
                "prompt_tokens": getattr(getattr(response, "usage", None), "prompt_tokens", None),
                "completion_tokens": getattr(
                    getattr(response, "usage", None), "completion_tokens", None
                ),
                "total_tokens": getattr(getattr(response, "usage", None), "total_tokens", None),
            }.items()
            if value is not None
        },
    )
