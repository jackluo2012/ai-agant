"""实验 8-7 规范重复真实模型活动证据验证"""

import sys
import os

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parent


def test_canonical_repeated_real_model_campaign_closes_all_gates():
    """
    测试规范的重复真实模型活动通过所有门禁

    验证：
    - 执行模式正确
    - 使用了预期的种子
    - 运行数量正确
    - API 调用数量正确
    - 实验被接受
    - 所有门禁通过
    - 收据数量和唯一性正确
    - 凭证值未记录
    - SHA256 校验和匹配
    - 统计指标符合预期
    """
    run_dir = ROOT / "validation" / "real_seeded_campaign"
    evidence_path = run_dir / "evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert evidence["execution_mode"] == "repeated_seeded_real_model_longitudinal_campaign"
    assert evidence["seeds"] == [8601, 8602, 8603]
    assert len(evidence["runs"]) == 9
    assert evidence["cost"]["api_calls"] == 126
    assert evidence["accepted"] is True
    assert all(evidence["gates"].values())

    receipts = [receipt for run in evidence["runs"] for receipt in run["raw_api_receipts"]]
    assert len(receipts) == 126
    assert len({receipt["response"]["id"] for receipt in receipts}) == 126
    assert all(not receipt["backend"]["credential_value_recorded"] for receipt in receipts)

    expected_sha = (run_dir / "evidence.sha256").read_text(encoding="utf-8").split()[0]
    assert expected_sha == hashlib.sha256(evidence_path.read_bytes()).hexdigest()

    latest_sha = (ROOT / "validation" / "latest.sha256").read_text(encoding="utf-8").split()[0]
    assert latest_sha == hashlib.sha256((ROOT / "validation" / "latest.json").read_bytes()).hexdigest()

    stats = evidence["statistics"]["by_arm"]
    assert stats["evolving"]["rule_replacement_accuracy"]["mean"] == 1.0
    assert stats["append_only"]["obsolete_rule_reference_rate"]["mean"] == 1.0
    assert evidence["cost"]["total_tokens"] > 0
