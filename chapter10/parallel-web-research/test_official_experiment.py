"""官方验收战役（2026-07-30 运行）的证据回放校验。

注意：本测试锚定的是历史运行快照。其中 runtime_source_sha256 绑定的是
当次运行的源码哈希；迁移后源码已经过统一 LLM 封装改造与中文化，
若要让 test_official_manifest_binds_artifacts_and_runtime_sources 重新
通过，需要重新运行 run_official_experiment.py 生成新的运行证据。
"""

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUN = ROOT / "validation" / "runs" / "exp10-4-real-receipts-20260730-v2"


def sha256_bytes(value: bytes) -> str:
    """计算字节串的 SHA-256 摘要。"""
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value) -> bytes:
    """把任意 JSON 值序列化为稳定的规范字节串（排序键、紧凑分隔符）。"""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def test_official_manifest_binds_artifacts_and_runtime_sources():
    """清单必须绑定产物哈希，且与运行时源码哈希一致（历史快照锚定）。"""
    manifest = json.loads((RUN / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["acceptance"] == {
        "overall_status": "pass",
        "passed_gates": 12,
        "total_gates": 12,
    }
    for name, expected in manifest["artifact_sha256"].items():
        assert sha256_bytes((RUN / name).read_bytes()) == expected
    for name, expected in manifest["runtime_source_sha256"].items():
        assert sha256_bytes((ROOT / name).read_bytes()) == expected


def test_official_receipts_are_raw_hashed_and_cover_all_three_phases():
    """原始凭证必须带哈希且覆盖三个阶段：并行 / 串行 / 级联压测。"""
    browser = json.loads((RUN / "browser_receipts.json").read_text(encoding="utf-8"))["receipts"]
    llm = json.loads((RUN / "llm_receipts.json").read_text(encoding="utf-8"))["receipts"]
    successful = [item for item in llm if item["kind"] == "llm_chat_completion"]

    # 浏览器观测：三个阶段齐全，逐条正文字节数与哈希可复算
    assert len(browser) == 24
    assert {item["phase"] for item in browser} == {
        "default_parallel", "default_serial", "cascade_stress",
    }
    for item in browser:
        raw = item["rendered_body_text"].encode("utf-8")
        assert len(raw) == item["rendered_body_bytes"]
        assert sha256_bytes(raw) == item["rendered_body_sha256"]

    # LLM 调用：三次成功调用响应 ID 各不相同、用量非零、请求/响应哈希可复算
    assert len(successful) == 3
    assert len({item["response_id"] for item in successful}) == 3
    assert {item["context"]["phase"] for item in successful} == {
        "default_parallel", "default_serial", "cascade_stress",
    }
    for item in successful:
        assert item["response"]
        assert item["usage"]["total_tokens"] > 0
        assert sha256_bytes(canonical_bytes(item["request"])) == item["request_sha256"]
        assert sha256_bytes(canonical_bytes(item["response"])) == item["response_sha256"]


def test_official_acceptance_and_latest_pointer_are_consistent_and_credential_free():
    """验收状态、latest 指针与清单哈希一致，且全部产物无凭证泄漏。"""
    evidence = json.loads((RUN / "evidence.json").read_text(encoding="utf-8"))
    latest = json.loads((ROOT / "validation" / "latest.json").read_text(encoding="utf-8"))
    assert evidence["overall_status"] == "pass"
    assert all(item["status"] == "pass" for item in evidence["gates"].values())
    assert evidence["measured_speedup"] > 1
    assert latest["run_id"] == evidence["run_id"]
    assert latest["manifest_sha256"] == sha256_bytes((RUN / "manifest.json").read_bytes())

    # 凭证泄漏扫描：不允许出现明文 api_key/authorization 字段或 Bearer 令牌
    combined = b"\n".join(path.read_bytes() for path in RUN.iterdir() if path.is_file())
    assert not re.search(rb'(?i)"(?:api[_-]?key|authorization)"\s*:\s*"(?!<redacted>|null|")[^"]+"', combined)
    assert not re.search(rb'(?i)bearer\s+[a-z0-9._~+/=-]{16,}', combined)
