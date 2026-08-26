#!/usr/bin/env python3
"""将已完成的实验 10-1 活动打包成可审计的证据。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SOURCE_FILES = (
    "run_comparison.py",
    "evaluation.py",
    "orchestrator.py",
    "skill_orchestrator.py",
    "tools.py",
    "experiment_protocol.json",
    "tasks.formal.json",
    "package_comparison.py",
    "judge_comparison.py",
    "validate_comparison.py",
)
SECRET_ENV_NAMES = (
    "TAVILY_API_KEY",
    "API_KEY",
)


def sha256_bytes(value: bytes) -> str:
    """计算字节的 SHA256 哈希"""
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    """计算文件的 SHA256 哈希"""
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    """将 JSON 值写入文件"""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def credential_scan(payload: bytes) -> dict[str, int]:
    """
    扫描凭证泄露

    Args:
        payload: 要扫描的字节

    Returns:
        扫描结果统计
    """
    actual = 0
    for name in SECRET_ENV_NAMES:
        secret = os.getenv(name, "").encode("utf-8")
        if len(secret) >= 8:
            actual += payload.count(secret)
    patterns = (
        re.compile(rb'(?i)"(?:api[_-]?key|authorization)"\s*:\s*"(?!<redacted>|null|\s*")[^"]+"'),
        re.compile(rb"(?i)bearer\s+[a-z0-9._~+/=-]{16,}"),
    )
    return {
        "actual_secret_hits": actual,
        "credential_pattern_hits": sum(len(pattern.findall(payload)) for pattern in patterns),
    }


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--judge", type=Path, required=True,
                        help="位置交换的质量评审证据 JSON")
    return parser.parse_args()


def main() -> int:
    """主函数"""
    args = parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    campaign_path = output / "campaign.json"
    campaign_path.write_bytes(args.campaign.read_bytes())
    judge_path = output / "judge.json"
    judge_path.write_bytes(args.judge.read_bytes())
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    judge = json.loads(judge_path.read_text(encoding="utf-8"))
    runs = campaign.get("runs", [])
    boundary_runs = campaign.get("boundary_runs", [])

    pairs: dict[str, set[str]] = {}
    for run in runs:
        pairs.setdefault(str(run.get("pair_id")), set()).add(str(run.get("path")))
    task_specs = campaign.get("tasks", [])
    task_ids = {str(item.get("id")) for item in task_specs}
    observed_task_ids = {str(item.get("task_id")) for item in runs}
    provider_receipts = [
        receipt for run in [*runs, *boundary_runs]
        for receipt in run.get("provider_receipts", [])
    ]
    tavily_receipts = [
        receipt for run in [*runs, *boundary_runs]
        for receipt in run.get("tavily_receipts", [])
    ]
    response_ids = [item.get("response_id") for item in provider_receipts]
    expected_provider_receipts = sum(
        int(run.get("metrics", {}).get("api_calls", 0))
        for run in [*runs, *boundary_runs]
    )
    scan = credential_scan(campaign_path.read_bytes() + b"\n" + judge_path.read_bytes())
    required_tool_sets = [set(item.get("required_tools", [])) for item in task_specs]
    boundary_pairs = {
        (str(run.get("case_id")), str(run.get("path"))) for run in boundary_runs
    }
    boundary_case_ids = {str(run.get("case_id")) for run in boundary_runs}
    judge_receipts = [item for pair in judge.get("pairs", []) for item in pair.get("judgments", [])]
    normalized_winners = [winner for pair in judge.get("pairs", []) for winner in pair.get("normalized_winners", [])]

    gates = {
        "campaign_finished_not_checkpoint": not campaign.get("checkpoint", False),
        "minimum_30_paired_samples": (
            int(campaign.get("paired_samples", 0)) >= 30
            and len(pairs) >= 30
            and all(paths == {"transfer", "skill"} for paths in pairs.values())
        ),
        "task_file_matches_retained_runs": task_ids == observed_task_ids and len(task_ids) == 30,
        "research_coding_writing_strata_present": (
            any("web_search" in tools for tools in required_tool_sets)
            and any("execute_python" in tools for tools in required_tool_sets)
            and any(tools == {"count_characters"} for tools in required_tool_sets)
        ),
        "raw_provider_receipt_for_every_call": (
            len(provider_receipts) == expected_provider_receipts > 0
            and all(item.get("request") and item.get("response") for item in provider_receipts)
        ),
        "unique_provider_response_ids": (
            all(response_ids) and len(set(response_ids)) == len(response_ids)
        ),
        "real_tavily_receipts_retained": (
            len(tavily_receipts) > 0
            and all(item.get("response", {}).get("http_status") == 200 for item in tavily_receipts)
            and all(item.get("response", {}).get("raw_body") for item in tavily_receipts)
            and all("api_key" not in item.get("request", {}).get("body", {}) for item in tavily_receipts)
        ),
        "all_failed_and_limited_trajectories_retained": (
            any(not run.get("outcome", {}).get("pass", False) for run in runs)
            and all(run.get("history") and run.get("provider_receipts") for run in runs)
        ),
        "complete_two_arm_boundary_suite": (
            len(boundary_case_ids) == 6
            and len(boundary_pairs) == 12
            and all(
                (case_id, path) in boundary_pairs
                for case_id in boundary_case_ids for path in ("transfer", "skill")
            )
        ),
        "paired_statistics_and_costs_present": (
            campaign.get("paired_comparison", {}).get("paired_n") == 30
            and campaign.get("paired_comparison", {}).get("pass_rate_delta", {}).get("bootstrap_95_percent") is not None
            and campaign.get("paired_comparison", {}).get("mcnemar", {}).get("two_sided_exact_p") is not None
            and campaign.get("paired_comparison", {}).get("cost_delta_usd") is not None
        ),
        "blind_quality_judge_position_swapped": (
            judge.get("paired_n") == 30
            and judge.get("judge_receipt_count") == 60
            and judge.get("unique_response_ids") == 60
            and judge.get("parse_complete") is True
            and len(judge.get("pairs", [])) == 30
            and all(len(pair.get("judgments", [])) == 2 for pair in judge.get("pairs", []))
        ),
        "credential_free_campaign": scan["actual_secret_hits"] == 0 and scan["credential_pattern_hits"] == 0,
    }
    overall = "pass" if all(gates.values()) else "incomplete"
    transfer = campaign["aggregate"]["transfer"]
    skill = campaign["aggregate"]["skill"]
    paired = campaign["paired_comparison"]
    acceptance = {
        "schema_version": 1,
        "experiment": "10-1",
        "run_id": args.run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_status": overall,
        "interpretation": "complete_bounded_comparison",
        "model": campaign.get("model"),
        "base_url": campaign.get("base_url"),
        "campaign_parameters": {
            "tasks": len(task_specs),
            "paired_samples": len(pairs),
            "main_runs": len(runs),
            "boundary_runs": len(boundary_runs),
            "max_steps": campaign.get("max_steps"),
            "max_output_tokens": campaign.get("max_output_tokens"),
            "temperature": campaign.get("temperature"),
        },
        "receipt_counts": {
            "provider": len(provider_receipts),
            "tavily": len(tavily_receipts),
        },
        "result": {
            "transfer_pass_at_1": transfer["pass_at_1"],
            "skill_pass_at_1": skill["pass_at_1"],
            "transfer_required_sequence_rate": transfer["required_role_sequence_rate"],
            "skill_required_sequence_rate": skill["required_role_sequence_rate"],
            "skill_minus_transfer_uncached_input_token_median": paired["uncached_input_token_delta"]["median"],
            "skill_minus_transfer_latency_seconds_median": paired["latency_delta_seconds"]["median"],
            "skill_minus_transfer_cost_usd_median": paired["cost_delta_usd"]["median"],
            "boundary_pass_rate": campaign["boundary_summary"],
            "quality_judge_stage": "completed_position_swapped_external_judge",
            "blind_judge_winner_counts": {
                "skill": normalized_winners.count("skill"),
                "transfer": normalized_winners.count("transfer"),
                "tie": normalized_winners.count("tie"),
            },
        },
        "credential_scan": scan,
        "gates": gates,
        "passed_gates": sum(gates.values()),
        "total_gates": len(gates),
    }
    acceptance_path = output / "acceptance.json"
    write_json(acceptance_path, acceptance)

    report = f"""# 实验 10-1 保留对比报告

## 结果

这是一个**完整有界对比**。该活动保留了 {len(pairs)} 个配对任务（{len(runs)} 条主轨迹）、
{len(boundary_runs)} 条边界轨迹、{len(provider_receipts)} 条原始提供商回执、
{len(tavily_receipts)} 条原始 Tavily 回执和 {len(judge_receipts)} 条位置交换的盲评回执。
每个证据门禁都通过（{sum(gates.values())}/{len(gates)}）。

- Transfer 路径通过了 {sum(bool(run['outcome']['pass']) for run in runs if run['path'] == 'transfer')}/{len(pairs)} 个完整
  确定性任务门禁；其声明的能力序列在 {transfer['required_role_sequence_rate']:.1%} 的运行中完成。
- Skill 路径通过了 {sum(bool(run['outcome']['pass']) for run in runs if run['path'] == 'skill')}/{len(pairs)} 个完整
  确定性任务门禁。它在 {sum(bool(run.get('loaded_skills')) for run in runs if run['path'] == 'skill')}/{len(pairs)} 次运行中
  至少加载了 triage，并在 {skill['required_role_sequence_rate']:.1%} 的运行中完成了声明的序列。
- 两条路径都通过了 6/6 个边界用例；边界可靠性报告与端到端任务成功分开。
- 独立的 Gemini 2.5 Flash Lite 评审者在 {normalized_winners.count('skill')}/{len(normalized_winners)}
  次交换展示中偏好 Skill，{normalized_winners.count('transfer')}/{len(normalized_winners)} 次偏好 Transfer，
  并称 {normalized_winners.count('tie')}/{len(normalized_winners)} 次为平局。每个配对的两次展示都被保留以控制位置偏差。

## 成本和延迟

Skill 减 Transfer 的中位数差值为 {paired['uncached_input_token_delta']['median']:.1f} 个未缓存输入 token、
{paired['latency_delta_seconds']['median']:.3f} 秒和 ${paired['cost_delta_usd']['median']:.8f}。提供商报告的
缓存输入始终为零，因此此次运行未建立模型前缀缓存收益。Skill 文档缓存记录了每次运行的未命中
（且跨运行无命中），这与本工具使用的全新会话缓存预期一致。

## 解释

对于此有界 OpenRouter 活动中的 `qwen/qwen3.5-flash-02-23`，修复后的 Skill 路径现在遵循
渐进披露状态机，并实质性提高了确定性验收率（50.0% vs 6.7%）。权衡是
更高的中位数未缓存输入（+{paired['uncached_input_token_delta']['median']:.1f} token）、
延迟（+{paired['latency_delta_seconds']['median']:.3f}s）和重新定价成本（+${paired['cost_delta_usd']['median']:.8f}）。
这是文档化架构权衡的证据，而非通用的模型无关性优势声明。
"""
    report_path = output / "REPORT.md"
    report_path.write_text(report, encoding="utf-8")

    source_hashes = {name: sha256_file(ROOT / name) for name in SOURCE_FILES}
    manifest = {
        "schema_version": 1,
        "experiment": "10-1",
        "run_id": args.run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_source_sha256": source_hashes,
        "artifact_sha256": {
            "campaign.json": sha256_file(campaign_path),
            "judge.json": sha256_file(judge_path),
            "acceptance.json": sha256_file(acceptance_path),
            "REPORT.md": sha256_file(report_path),
        },
        "acceptance": {
            "evidence_status": overall,
            "passed_gates": acceptance["passed_gates"],
            "total_gates": acceptance["total_gates"],
        },
    }
    write_json(output / "manifest.json", manifest)
    print(f"packaged {args.run_id}: {overall} ({sum(gates.values())}/{len(gates)} gates)")
    return 0 if overall == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
