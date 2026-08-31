"""
证据约束的教师信息抽取（真实 LLM 调用）
========================================

基于浏览器实际渲染的页面文本，由真实配置的 LLM 端点做证据约束抽取。
LLM 配置统一来自项目根目录的 .env（通过 llm.client 封装读取），本模块
不硬编码任何 API 密钥或端点地址。

说明：
- 项目为异步架构（asyncio + Playwright），统一封装 ``get_llm_client()``
  返回的是同步客户端，因此这里读取统一配置后构造 ``AsyncOpenAI``
  异步客户端，配置来源保持唯一（项目根目录 .env）。
"""

from __future__ import annotations

import json
import sys
import os
import time
from typing import Callable, Dict, Optional

# 添加项目根目录到路径，确保能导入统一的 llm 封装模块
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径，便于独立运行时导入同目录模块
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from openai import AsyncOpenAI

try:
    from llm.client import get_llm_client
except ImportError:
    get_llm_client = None


# 回执写入函数类型：接收一个事件字典，用于留存原始调用凭证
ReceiptSink = Optional[Callable[[Dict[str, object]], None]]


def _async_client():
    """
    依据统一 LLM 配置构造异步客户端

    复用统一封装 get_llm_client() 完成密钥/端点/模型的解析
    （含多种 API Key 环境变量名的兼容处理），再据此构造异步客户端。

    Returns:
        (AsyncOpenAI 客户端, 模型名, 提供商名) 三元组

    Raises:
        RuntimeError: 统一配置模块缺失或 .env 未配置 API 密钥
    """
    if get_llm_client is None:
        raise RuntimeError("无法导入统一的 llm.client 封装，请检查项目根目录结构")
    # 统一封装内部会校验配置完整性，未配置时抛出带指引的错误
    sync_client = get_llm_client()
    client = AsyncOpenAI(
        api_key=sync_client.api_key,
        base_url=sync_client.base_url,
    )
    return client, sync_client.model_name, sync_client.provider


async def extract_profile(
    target: str,
    college: str,
    url: str,
    text: str,
    receipt_sink: ReceiptSink = None,
    call_context: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """只从浏览器实际渲染的文本中抽取教师信息

    确定性的人名出现门槛（先检查 target 是否出现在页面文本中）可以防止
    模型在页面并未真正包含目标人物时，凭参数化记忆"编造"出一份档案。

    Args:
        target: 要查找的教师姓名
        college: 目标所在院校名称
        url: 被抓取页面的 URL
        text: 浏览器渲染后的页面正文文本
        receipt_sink: 可选的回执回调，用于留存原始 LLM 请求/响应凭证
        call_context: 可选的调用上下文（阶段、worker_id、站点名等）

    Returns:
        LLM 返回的 JSON 结果字典（额外附上 provider 与 url 字段）

    Raises:
        RuntimeError: 页面文本缺少目标人名时返回 found=False；
            LLM 端点调用失败时抛出
    """
    # 确定性门槛：目标人名未出现在渲染文本中时，直接判定未找到
    if target.casefold() not in text.casefold():
        return {"found": False, "reason": "目标人名未出现在渲染页面中"}

    # 截断过长文本，避免超出模型上下文窗口
    clipped = text[:45_000]
    prompt = {
        "target": target,
        "site_college": college,
        "url": url,
        "rendered_page_text": clipped,
        "instruction": (
            "只允许使用 rendered_page_text 判断页面是否包含这位教师本人的档案。"
            "返回 JSON，键为 found、name、college、position、research、evidence。"
            "如果人名仅出现在链接或列表中，found 可为 true，但无证据支持的字段留空。"
            "evidence 必须是页面中的简短原文摘录。"
        ),
    }

    # 获取统一配置的异步客户端
    client, model, provider = _async_client()
    started = time.monotonic()
    try:
        # 构造请求参数；部分模型（如 kimi-k3）需要特定的温度/令牌上限
        kwargs = dict(
            model=model,
            messages=[{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
            response_format={"type": "json_object"},
        )
        if "kimi-k3" in model:
            kwargs.update(temperature=1, max_tokens=2048)
        response = await client.chat.completions.create(**kwargs)
        raw_response = response.model_dump(mode="json")
        # 留存原始调用凭证（请求/响应/用量/耗时），供验收审计使用
        if receipt_sink:
            receipt_sink({
                "kind": "llm_chat_completion",
                "context": dict(call_context or {}),
                "provider": provider,
                "request": kwargs,
                "response": raw_response,
                "response_id": response.id,
                "response_model": response.model,
                "usage": response.usage.model_dump(mode="json") if response.usage else None,
                "duration_seconds": round(time.monotonic() - started, 3),
            })
        content = response.choices[0].message.content or ""
        if not content.strip():
            raise ValueError("模型返回了空内容")
        result = json.loads(content)
        result["provider"] = provider
        result["url"] = url
        return result
    except Exception as exc:
        # 记录失败凭证后向上抛出，由上层协调器做错误隔离
        if receipt_sink:
            receipt_sink({
                "kind": "llm_chat_completion_error",
                "context": dict(call_context or {}),
                "provider": provider,
                "model": model,
                "error_type": type(exc).__name__,
                "duration_seconds": round(time.monotonic() - started, 3),
            })
        print(f"  [抽取] {provider} 调用失败：{type(exc).__name__}")
        raise RuntimeError(f"LLM 抽取端点调用失败：{type(exc).__name__}: {exc}") from exc
