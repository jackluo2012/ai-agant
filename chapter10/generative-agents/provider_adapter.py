"""OpenAI 兼容适配器：把上游遗留的 GPT-3 调用重定向到统一配置的当前模型。

固定 commit 的官方上游源码按 openai 0.27 的旧接口编写：
``openai.ChatCompletion.create`` / ``openai.Completion.create`` /
``openai.Embedding.create``。共享虚拟环境安装的是现代 SDK（openai >= 1.0），
本模块在 ``openai`` 包上注入同名兼容 shim，使上游代码零修改即可运行，
同时底层改用统一封装 ``llm.client.get_llm_client`` 的现代客户端发起真实调用。

每次逻辑调用的完整请求/响应都会以无凭据 JSONL 回执的形式落盘：凭据永不序列化，
回执保留提供商响应 ID、token 用量、时延与传输层重试；向量仅保留维度与内容哈希。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# 添加项目根目录到路径，确保可以导入统一的 LLM 封装模块
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from llm.client import get_llm_client

# 已知凭据的脱敏正则（回执中永远不落盘真实密钥）
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
)
# 可重试的瞬态错误类型名称（传输层故障，与逻辑错误区分）
_TRANSIENT_ERROR_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "RateLimitError",
    "ServiceUnavailableError",
    "Timeout",
}
# 同一逻辑调用内传输层重试的最大次数
_MAX_TRANSPORT_ATTEMPTS = 5
# 阿里云兼容端点上启用思考模式的模型需要显式关闭，避免上游解析非正文输出
_THINKING_OFF_PROVIDERS = {"aliyun", "custom"}


def _sha256_json(value: Any) -> str:
    """计算 JSON 规范化表示的 SHA-256 哈希。"""
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _redact_text(value: str) -> str:
    """把文本中疑似凭据的片段替换为占位符。"""
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("<redacted-credential>", value)
    return value


def _plain(value: Any) -> Any:
    """把任意响应对象递归转换为可 JSON 序列化的纯数据结构。"""
    if hasattr(value, "to_dict_recursive"):
        return value.to_dict_recursive()
    # 现代 SDK 返回 pydantic 模型，统一转成字典
    if hasattr(value, "model_dump"):
        converted = value.model_dump()
        return {str(key): _plain(item) for key, item in converted.items()}
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_text(str(value))


class ReceiptRecorder:
    """为一个 checkpoint 追加写入崩溃容忍的 JSONL 调用回执。"""

    def __init__(self) -> None:
        self._path: Path | None = None
        self._lock = threading.Lock()

    def set_path(self, path: Path) -> None:
        """绑定当前 checkpoint 的回执文件路径。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        # 没有模型调用的 checkpoint 同样有效：立即物化回执文件，
        # 让运行器仍能压缩并保留一个空的 JSONL 文件。
        path.touch(exist_ok=True)
        self._path = path

    def record(
        self,
        *,
        kind: str,
        request: dict[str, Any],
        started: float,
        response: Any | None = None,
        error: BaseException | None = None,
        transport_retries: list[dict[str, Any]] | None = None,
    ) -> None:
        """追加一行回执并强制刷盘，保证崩溃后已写入内容不丢失。"""
        if self._path is None:
            return
        request_plain = _plain(request)
        response_plain = _plain(response) if response is not None else None
        # 向量回执只保留维度与哈希，不重复存储每一个浮点数
        if kind == "embedding" and isinstance(response_plain, dict):
            compact_data = []
            for row in response_plain.get("data", []):
                vector = row.get("embedding", []) if isinstance(row, dict) else []
                compact_data.append(
                    {
                        "index": row.get("index") if isinstance(row, dict) else None,
                        "object": row.get("object") if isinstance(row, dict) else None,
                        "embedding_dimensions": len(vector),
                        "embedding_sha256": _sha256_json(vector),
                    }
                )
            response_plain["data"] = compact_data
        row = {
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "kind": kind,
            "request": request_plain,
            "request_sha256": _sha256_json(request_plain),
            "response": response_plain,
            "latency_seconds": round(time.perf_counter() - started, 3),
            "success": error is None,
            "transport_retries": transport_retries or [],
            "error": (
                None
                if error is None
                else {
                    "type": type(error).__name__,
                    "message": _redact_text(str(error))[:1000],
                }
            ),
        }
        encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())


# 模块级单例：运行器通过它切换每个 checkpoint 的回执文件
RECORDER = ReceiptRecorder()


def _resolve_chat_model(client: Any, override: str | None) -> str:
    """解析对话模型名：显式参数 > 章节环境变量 > 统一配置的 LLM_MODEL。"""
    return (
        override
        or os.environ.get("CHAPTER10_CHAT_MODEL")
        or client.model_name
    )


def _resolve_embedding_model(client: Any, override: str | None) -> str:
    """解析向量模型名：显式参数 > 章节环境变量 > 按提供商推断的默认值。"""
    resolved = override or os.environ.get("CHAPTER10_EMBEDDING_MODEL")
    if resolved:
        return resolved
    if client.provider in _THINKING_OFF_PROVIDERS:
        # 阿里云/自定义兼容端点的默认向量模型
        return "text-embedding-v4"
    raise ValueError(
        "未指定文本向量模型。请通过以下方式之一设置：\n"
        "1. 环境变量: export CHAPTER10_EMBEDDING_MODEL='text-embedding-v4'\n"
        "2. .env 文件: CHAPTER10_EMBEDDING_MODEL=text-embedding-v4"
    )


def install(
    *,
    receipt_path: Path,
    chat_model: str | None = None,
    embedding_model: str | None = None,
) -> None:
    """把上游遗留的 GPT-3/GPT-4 调用重定向到统一配置的当前模型。

    Args:
        receipt_path: 当前逻辑调用的回执 JSONL 文件路径
        chat_model: 对话模型名（可选，默认读取统一配置）
        embedding_model: 向量模型名（可选，默认按提供商推断）

    Raises:
        ValueError: 当统一配置缺少 API 密钥、端点或向量模型时
    """
    # 统一客户端：凭据与端点只来自项目根目录 .env
    client = get_llm_client()
    resolved_chat_model = _resolve_chat_model(client, chat_model)
    resolved_embedding_model = _resolve_embedding_model(client, embedding_model)
    # 单次物理请求的客户端超时（秒），可用章节环境变量覆盖
    request_timeout = float(os.environ.get("CHAPTER10_PROVIDER_TIMEOUT_SECONDS", "90"))
    RECORDER.set_path(receipt_path)

    # 兼容端点上需要显式关闭思考模式，其余提供商不发送该字段
    extra_body = (
        {"enable_thinking": False}
        if client.provider in _THINKING_OFF_PROVIDERS
        else None
    )

    def _build_chat_payload(kwargs: dict[str, Any]) -> dict[str, Any]:
        """把上游 0.27 风格的调用参数映射为现代 SDK 的对话请求。"""
        payload: dict[str, Any] = {
            "model": resolved_chat_model,
            "messages": kwargs.get("messages")
            or [{"role": "user", "content": kwargs.get("prompt", "")}],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 512),
            "top_p": kwargs.get("top_p", 1),
            "frequency_penalty": kwargs.get("frequency_penalty", 0),
            "presence_penalty": kwargs.get("presence_penalty", 0),
            "timeout": request_timeout,
        }
        # 上游仅在特定提示词中传递停止序列
        if kwargs.get("stop"):
            payload["stop"] = kwargs["stop"]
        if extra_body:
            payload["extra_body"] = dict(extra_body)
        return payload

    def call_with_transient_retries(
        *, kind: str, request: dict[str, Any], function: Any
    ) -> Any:
        """在同一逻辑调用内对瞬态传输故障做有界指数退避重试。"""
        started = time.perf_counter()
        retries: list[dict[str, Any]] = []
        for attempt in range(1, _MAX_TRANSPORT_ATTEMPTS + 1):
            try:
                response = function()
            except BaseException as exc:
                # 仅对列出的瞬态错误重试；逻辑错误立即落盘并抛出
                transient = type(exc).__name__ in _TRANSIENT_ERROR_NAMES
                if transient and attempt < _MAX_TRANSPORT_ATTEMPTS:
                    retries.append(
                        {
                            "attempt": attempt,
                            "type": type(exc).__name__,
                            "message": _redact_text(str(exc))[:1000],
                        }
                    )
                    time.sleep(min(4.0, 0.5 * (2 ** (attempt - 1))))
                    continue
                RECORDER.record(
                    kind=kind,
                    request=request,
                    started=started,
                    error=exc,
                    transport_retries=retries,
                )
                raise
            RECORDER.record(
                kind=kind,
                request=request,
                started=started,
                response=response,
                transport_retries=retries,
            )
            return response
        raise AssertionError("不可达的提供商重试循环")

    def chat_create(**kwargs: Any) -> Any:
        """兼容 ``openai.ChatCompletion.create`` 的对话入口。"""
        # 回执记录脱敏后的映射参数；真实调用使用同一负载
        payload = _build_chat_payload(kwargs)
        return call_with_transient_retries(
            kind="chat",
            request=_plain(payload),
            function=lambda: client.chat.completions.create(**payload),
        )

    def completion_create(**kwargs: Any) -> Any:
        """把遗留的补全入口映射为对话接口，并模拟 0.27 的文本响应形态。"""
        payload = _build_chat_payload(kwargs)
        # 回执沿用对话请求的形态，仅额外记录被丢弃的提示词参数名
        request = _plain(payload)
        request["legacy_completion_prompt_chars"] = len(kwargs.get("prompt", ""))
        response = call_with_transient_retries(
            kind="chat",
            request=request,
            function=lambda: client.chat.completions.create(**payload),
        )
        # 上游按 0.27 的补全响应访问 choices[0].text
        content = response["choices"][0]["message"]["content"]
        return SimpleNamespace(choices=[SimpleNamespace(text=content)])

    def embedding_create(**kwargs: Any) -> Any:
        """兼容 ``openai.Embedding.create`` 的向量入口。"""
        payload: dict[str, Any] = {
            "model": resolved_embedding_model,
            "input": kwargs.get("input"),
            # 固定输出维度，保证检索相似度在整个实验中可比
            "dimensions": 1024,
            "timeout": request_timeout,
        }
        if extra_body:
            payload["extra_body"] = dict(extra_body)
        request = _plain(payload)
        return call_with_transient_retries(
            kind="embedding",
            request=request,
            function=lambda: client.embeddings.create(**payload),
        )

    # 上游代码通过 ``openai.ChatCompletion.create(...)`` 等属性访问旧入口，
    # 在现代 SDK 的模块对象上注入同名 shim 即可让上游零修改运行。
    class _LegacyChatCompletion:
        create = staticmethod(chat_create)

    class _LegacyCompletion:
        create = staticmethod(completion_create)

    class _LegacyEmbedding:
        create = staticmethod(embedding_create)

    import openai

    openai.ChatCompletion = _LegacyChatCompletion  # type: ignore[attr-defined]
    openai.Completion = _LegacyCompletion  # type: ignore[attr-defined]
    openai.Embedding = _LegacyEmbedding  # type: ignore[attr-defined]
