import hashlib
import json
import shutil
from pathlib import Path

import pytest
from validate_acceptance import ValidationFailure, validate_run

ROOT = Path(__file__).parent
# 历史运行由原书仓库（ai-agent-book）时期的源码产生；其 source_sha256 绑定
# 原书源码，与迁移后的工作区源码天然不同，因此参考校验跳过源码哈希部分。
RUN = ROOT / "validation/runs/exp10-3-webrtc-raw-20260731-v4"


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _rehash_artifact(run_dir: Path, name: str) -> None:
    """按改动后的文件内容重算 artifact 哈希并写回 manifest。"""
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_sha256"][name] = hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
    _write(manifest_path, manifest)


def _copy_run(tmp_path: Path) -> Path:
    destination = tmp_path / "run"
    shutil.copytree(RUN, destination)
    return destination


def test_standalone_validator_proves_raw_receipt_consistency() -> None:
    result = validate_run(RUN, source_root=ROOT, verify_source_hashes=False)
    assert result["status"] == "pass"
    assert result["checks"]["source_hashes"] == "skipped"
    assert result["checks"]["raw_ark_request_tool_choice_auto"] == "pass"
    assert result["checks"]["raw_arguments_normalize_to_decision"] == "pass"


def test_validator_rejects_semantically_modified_raw_receipt(tmp_path: Path) -> None:
    """篡改原始响应 ID 后，即使重算哈希也必须被拒绝。"""
    run_dir = _copy_run(tmp_path)
    path = run_dir / "raw_decision_response.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["response"]["id"] = "tampered-response-id"
    _write(path, receipt)
    _rehash_artifact(run_dir, path.name)

    with pytest.raises(ValidationFailure, match="响应 ID"):
        validate_run(run_dir, source_root=ROOT, verify_source_hashes=False)


def test_validator_rejects_semantically_modified_normalized_decision(tmp_path: Path) -> None:
    """篡改规范化 decision 的 purpose 后必须被拒绝。"""
    run_dir = _copy_run(tmp_path)
    path = run_dir / "decision.json"
    decision = json.loads(path.read_text(encoding="utf-8"))
    decision["purpose"] = "被篡改的规范化目的"
    _write(path, decision)
    _rehash_artifact(run_dir, path.name)

    with pytest.raises(ValidationFailure, match="purpose"):
        validate_run(run_dir, source_root=ROOT, verify_source_hashes=False)


def test_validator_rejects_modified_manifest_hash(tmp_path: Path) -> None:
    """manifest 中的哈希被改写为占位值后必须被拒绝。"""
    run_dir = _copy_run(tmp_path)
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["artifact_sha256"]["raw_decision_request.json"] = "0" * 64
    _write(path, manifest)

    with pytest.raises(ValidationFailure, match="artifact_sha256"):
        validate_run(run_dir, source_root=ROOT, verify_source_hashes=False)


def test_validator_rejects_unbound_retained_artifact(tmp_path: Path) -> None:
    """出现未绑定进 manifest 的多余留痕文件时必须被拒绝。"""
    run_dir = _copy_run(tmp_path)
    (run_dir / "unbound_transcript.txt").write_text("unexpected", encoding="utf-8")

    with pytest.raises(ValidationFailure, match="文件集合不一致"):
        validate_run(run_dir, source_root=ROOT, verify_source_hashes=False)
