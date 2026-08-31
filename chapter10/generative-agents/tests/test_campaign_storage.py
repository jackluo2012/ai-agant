from __future__ import annotations

import json
from pathlib import Path

from supervise_campaigns import live_receipt_has_error


def test_runner_creates_movement_directory_after_fork():
    """运行器必须在分叉模拟之后、写入移动记录之前创建 movement 目录。"""
    source = Path(__file__).resolve().parents[1] / "run_campaign.py"
    text = source.read_text(encoding="utf-8")
    constructor = 'server = ReverieServer(status["current_sim"], sim_code)'
    mkdir = '(target_dir / "movement").mkdir(exist_ok=True)'
    assert constructor in text
    assert mkdir in text
    assert text.index(constructor) < text.index(mkdir)


def test_packager_retains_action_arena_compatibility_receipts():
    """打包器必须把行动场所兼容性回执一并收入证据包。"""
    source = Path(__file__).resolve().parents[1] / "package_evidence.py"
    text = source.read_text(encoding="utf-8")
    assert 'compatibility = output / "compatibility"' in text
    assert 'shutil.copytree(compatibility, destination / "compatibility")' in text


def test_supervisor_detects_provider_error_in_live_checkpoint(tmp_path):
    """监督器应能从实时回执中发现提供商错误并触发提前终止。"""
    status = tmp_path / "status" / "baseline.json"
    status.parent.mkdir()
    status.write_text(json.dumps({"completed_steps": 360}), encoding="utf-8")
    receipt = tmp_path / "receipts" / "baseline" / "steps_00360_00720.jsonl"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps({"success": True})
        + "\n"
        + json.dumps({"success": False})
        + "\n",
        encoding="utf-8",
    )
    assert live_receipt_has_error(tmp_path, "baseline", 17_280, 360) is True
    receipt.write_text(json.dumps({"success": True}) + "\n", encoding="utf-8")
    assert live_receipt_has_error(tmp_path, "baseline", 17_280, 360) is False
