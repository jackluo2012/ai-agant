from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from provider_adapter import ReceiptRecorder, install, get_llm_client


def make_fake_client(chat_create, embedding_create=None, provider="kimi"):
    """构造一个模拟统一客户端：只暴露适配器实际使用的接口。"""
    return SimpleNamespace(
        provider=provider,
        model_name="config-chat",
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
        embeddings=SimpleNamespace(
            create=embedding_create or (lambda **kwargs: None)
        ),
    )


def chat_response(kwargs):
    """构造一个最小可用的对话响应字典。"""
    return {
        "id": "chat-id",
        "model": kwargs["model"],
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
    }


def test_recorder_materializes_zero_call_checkpoint(tmp_path):
    """没有任何调用的 checkpoint 也应物化出空回执文件。"""
    receipt = tmp_path / "nested" / "empty.jsonl"
    recorder = ReceiptRecorder()
    recorder.set_path(receipt)
    assert receipt.is_file()
    assert receipt.read_bytes() == b""


def test_adapter_overrides_legacy_models_and_compacts_embeddings(tmp_path, monkeypatch):
    """旧入口应被重定向到配置模型，向量回执应压缩为维度与哈希。"""
    calls = []

    def chat_create(**kwargs):
        calls.append(("chat", kwargs))
        return chat_response(kwargs)

    def embedding_create(**kwargs):
        calls.append(("embedding", kwargs))
        return {
            "id": "embedding-id",
            "model": kwargs["model"],
            "data": [{"index": 0, "object": "embedding", "embedding": [0.1, 0.2]}],
            "usage": {"prompt_tokens": 1, "total_tokens": 1},
        }

    # 替换统一客户端工厂，保持测试离线
    monkeypatch.setattr(
        sys.modules["provider_adapter"],
        "get_llm_client",
        lambda: make_fake_client(chat_create, embedding_create, provider="kimi"),
    )
    # 模拟现代 SDK 的 openai 模块：安装后应出现旧命名空间 shim
    fake_openai = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    receipt = tmp_path / "calls.jsonl"
    install(
        receipt_path=receipt,
        chat_model="current-chat",
        embedding_model="current-embedding",
    )

    chat = fake_openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[])
    completion = fake_openai.Completion.create(model="text-davinci-003", prompt="hello")
    embedding = fake_openai.Embedding.create(model="text-embedding-ada-002", input=["x"])

    assert chat["id"] == "chat-id"
    # 补全入口被映射为对话接口，并以 0.27 的文本响应形态返回
    assert completion.choices[0].text == "ok"
    assert embedding["data"][0]["embedding"] == [0.1, 0.2]
    assert [call[1]["model"] for call in calls] == [
        "current-chat",
        "current-chat",
        "current-embedding",
    ]
    assert all(call[1]["timeout"] == 90 for call in calls)
    # kimi 提供商不应发送思考模式开关
    assert all("extra_body" not in call[1] for call in calls)
    rows = [json.loads(line) for line in receipt.read_text().splitlines()]
    assert len(rows) == 3
    assert all(row["success"] for row in rows)
    compact = rows[-1]["response"]["data"][0]
    assert compact["embedding_dimensions"] == 2
    assert "embedding" not in compact


def test_adapter_aliyun_provider_disables_thinking(tmp_path, monkeypatch):
    """阿里云兼容端点需要显式关闭思考模式。"""
    seen = []

    def chat_create(**kwargs):
        seen.append(kwargs)
        return chat_response(kwargs)

    monkeypatch.setattr(
        sys.modules["provider_adapter"],
        "get_llm_client",
        lambda: make_fake_client(chat_create, provider="aliyun"),
    )
    fake_openai = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    install(receipt_path=tmp_path / "calls.jsonl")

    fake_openai.ChatCompletion.create(model="legacy", messages=[])
    assert seen[0]["extra_body"] == {"enable_thinking": False}


def test_adapter_retries_transient_connection_and_records_one_logical_call(
    tmp_path, monkeypatch
):
    """瞬态传输错误应在同一逻辑调用内重试，回执只记一行。"""
    attempts = 0

    class APIConnectionError(Exception):
        pass

    def chat_create(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise APIConnectionError("connection closed")
        return {
            "id": "retry-success",
            "model": kwargs["model"],
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    monkeypatch.setattr(
        sys.modules["provider_adapter"],
        "get_llm_client",
        lambda: make_fake_client(chat_create, provider="kimi"),
    )
    monkeypatch.setattr("provider_adapter.time.sleep", lambda _: None)
    receipt = tmp_path / "retry.jsonl"
    fake_openai = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    install(
        receipt_path=receipt,
        chat_model="current-chat",
        embedding_model="current-embedding",
    )

    response = fake_openai.ChatCompletion.create(model="legacy", messages=[])
    rows = [json.loads(line) for line in receipt.read_text().splitlines()]
    assert response["id"] == "retry-success"
    assert attempts == 2
    assert len(rows) == 1
    assert rows[0]["success"] is True
    assert rows[0]["transport_retries"] == [
        {
            "attempt": 1,
            "type": "APIConnectionError",
            "message": "connection closed",
        }
    ]


def test_adapter_requires_embedding_model_for_unknown_providers(monkeypatch, tmp_path):
    """无法推断向量模型的提供商必须显式给出 CHAPTER10_EMBEDDING_MODEL。"""

    def chat_create(**kwargs):
        raise AssertionError("不应发起调用")

    monkeypatch.setattr(
        sys.modules["provider_adapter"],
        "get_llm_client",
        lambda: make_fake_client(chat_create, provider="kimi"),
    )
    monkeypatch.delenv("CHAPTER10_EMBEDDING_MODEL", raising=False)
    with pytest.raises(ValueError, match="CHAPTER10_EMBEDDING_MODEL"):
        install(receipt_path=tmp_path / "calls.jsonl")


def test_get_llm_client_is_imported_from_unified_module():
    """适配器必须使用统一封装的客户端工厂，而不是自建客户端。"""
    assert get_llm_client.__module__ == "llm.client"
