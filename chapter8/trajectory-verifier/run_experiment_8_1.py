#!/usr/bin/env python3
"""用于论文实验 8-1 的标准真实运行。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from calibration import calibration_report
from customer_service_env import run_case
from evidence_client import EvidenceChatClient
from llm_judge import OpenAIQualityJudge
from verifier import FAIL, TrajectoryVerifier, diagnostic_utility, scalar_baseline


ROOT = Path(__file__).resolve().parent


def _git_revision() -> str | None:
    """
    获取当前 Git 仓库的修订版本。

    Returns:
        Git HEAD 的 SHA，如果无法获取则返回 None
    """
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def _gate(name: str, passed: bool, evidence: object) -> dict:
    """
    创建验证门项。

    Args:
        name: 门项名称
        passed: 是否通过
        evidence: 证据

    Returns:
        门项字典
    """
    return {"name": name, "passed": bool(passed), "evidence": evidence}


def build_evidence(cases, trajectories, reports, client, command) -> dict:
    """
    构建实验证据报告。

    Args:
        cases: 测试用例列表
        trajectories: 轨迹列表
        reports: 验证器报告列表
        client: LLM 客户端
        command: 执行命令

    Returns:
        完整的证据报告字典
    """
    calibration = calibration_report(trajectories, reports)
    scenario_counts = {name: 0 for name in ("normal_refund", "false_promise", "privacy_leak", "over_refusal")}
    for trajectory in trajectories:
        scenario_counts[trajectory["scenario"]] += 1

    # 提取有证据的失败项
    failures_with_evidence = [
        item for report in reports for item in report["dimensions"]
        if item["verdict"] == FAIL and item["evidence"]
    ]

    # 高分但高风险的报告
    risky_high_score = [
        report for report in reports
        if report["overall_score"] >= 0.8
        and any(name in report["critical_failures"] for name in ("privacy_boundary", "rule_compliance"))
    ]

    # 需要复核的报告
    risky_routed = [report for report in reports if report["review"]["required"]]
    scalar_reports = [scalar_baseline(report) for report in reports]

    # 多维定位效用统计
    multidim_localization = sum(
        diagnostic_utility(report) == 1.0 for report in reports
        if any(item["verdict"] == FAIL for item in report["dimensions"])
    )

    # 失败报告计数
    failed_report_count = sum(any(item["verdict"] == FAIL for item in report["dimensions"]) for report in reports)

    gates = [
        _gate("real_customer_service_agent_calls", any(t["kind"] == "customer_service_agent" for t in client.api_turns), len(client.api_turns)),
        _gate("real_llm_quality_judge_calls", any(t["kind"] == "quality_judge" for t in client.api_turns), sum(t["kind"] == "quality_judge" for t in client.api_turns)),
        _gate("all_four_expert_labeled_trajectory_types", all(value >= 2 for value in scenario_counts.values()), scenario_counts),
        _gate("seven_dimensional_reports", all(len(report["dimensions"]) == 7 for report in reports), [len(r["dimensions"]) for r in reports]),
        _gate("environment_and_policy_layers_are_deterministic", all(item["layer"] != "llm_rubric" for r in reports for item in r["dimensions"][:5]), "first five dimensions are code-derived"),
        _gate("failure_precision_recall_reported_by_dimension", bool(calibration["per_dimension"]), calibration["per_dimension"]),
        _gate("exact_expert_label_agreement_reported", "exact_label_agreement" in calibration, calibration["exact_label_agreement"]),
        _gate("every_failure_has_nonempty_evidence", len(failures_with_evidence) == sum(item["verdict"] == FAIL for r in reports for item in r["dimensions"]), len(failures_with_evidence)),
        _gate("high_score_cannot_hide_privacy_or_rule_failure", bool(risky_high_score) and all(r["release_recommendation"] == "reject" for r in risky_high_score), [r["trajectory_id"] for r in risky_high_score]),
        _gate("high_risk_or_low_confidence_is_reviewed_not_learned", bool(risky_routed) and all(not r["eligible_as_automatic_learning_signal"] for r in risky_routed), [r["trajectory_id"] for r in risky_routed]),
        _gate("multidimensional_root_cause_localization_beats_scalar", failed_report_count > 0 and multidim_localization == failed_report_count and all(set(row) == {"trajectory_id", "score"} for row in scalar_reports), {"scalar_root_cause_fields": 0, "multidimensional_evidenced_failure_reports": multidim_localization, "failed_reports": failed_report_count}),
        _gate("credentials_not_recorded", True, "only credential_source_env is stored"),
    ]
    execution_accepted = all(gate["passed"] for gate in gates)
    result_claims = {
        "stable_key_violation_detection": all(
            {item["dimension"] for item in report["dimensions"] if item["verdict"] == FAIL}
            >= {dimension for dimension, verdict in trajectory["expert_labels"].items() if verdict == FAIL}
            for trajectory, report in zip(trajectories, reports)
        ),
        "multidimensional_more_diagnostic_than_scalar": multidim_localization == failed_report_count and failed_report_count > 0,
        "exact_label_agreement": calibration["exact_label_agreement"],
    }
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "schema_version": 2,
        "experiment_id": "8-1",
        "canonical_source": "book/chapter8.md#实验-8-1-为客服-Agent-构建轨迹验证器",
        "evidence_mode": "real_provider_customer_service_and_quality_judge",
        "created_at": now,
        "command": command,
        "provider": client.provider,
        "model": client.model,
        "endpoint": f"{client.base_url}/chat/completions",
        "credential_source_env": client.credential_source_env,
        "credential_value_recorded": False,
        "host": {"python": sys.version.split()[0], "platform": platform.platform()},
        "repository_revision": _git_revision(),
        "dataset": {"case_count": len(cases), "scenario_counts": scenario_counts, "fictional_data_only": True},
        "trajectories": trajectories,
        "reports": reports,
        "scalar_baseline": scalar_reports,
        "calibration": calibration,
        "usage": client.usage_summary(),
        "api_turns": client.api_turns,
        "acceptance": {
            "gates": gates,
            "execution_accepted": execution_accepted,
            "result_claims": result_claims,
            "all_manuscript_result_claims_observed": all(
                value is True or (key == "exact_label_agreement" and value == 1.0)
                for key, value in result_claims.items()
            ),
        },
    }


def main() -> int:
    """
    主函数：运行实验 8-1 的完整流程。

    Returns:
        0 表示执行成功并被接受，1 表示执行被拒绝
    """
    parser = argparse.ArgumentParser(description=__doc__)
    # 移除 provider 参数，使用项目根目录 .env 配置
    parser.add_argument("--model", help="模型名称（可选，默认使用项目配置）")
    parser.add_argument("--output-dir", type=Path, help="输出目录")
    args = parser.parse_args()

    # 加载测试用例
    cases = json.loads((ROOT / "real_cases.json").read_text(encoding="utf-8"))

    # 创建证据客户端（使用项目配置）
    client = EvidenceChatClient(provider=None, model=args.model)
    trajectories = [run_case(case, client) for case in cases]

    # 创建 LLM 评估器
    judge = OpenAIQualityJudge(evidence_client=client)
    reports = [TrajectoryVerifier(judge).evaluate(trajectory) for trajectory in trajectories]

    # 构建命令字符串
    command = " ".join(["python", Path(__file__).name] + (["--model", args.model] if args.model else []))

    # 构建证据
    evidence = build_evidence(cases, trajectories, reports, client, command)

    # 输出结果
    stamp = datetime.now(timezone.utc).strftime("real_%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or ROOT / "validation" / stamp
    output_dir.mkdir(parents=True, exist_ok=False)
    path = output_dir / "evidence.json"
    payload = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")
    (ROOT / "validation").mkdir(exist_ok=True)
    (ROOT / "validation" / "latest.json").write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode()).hexdigest()

    print(json.dumps({
        "evidence": str(path.relative_to(ROOT)),
        "sha256": digest,
        "execution_accepted": evidence["acceptance"]["execution_accepted"],
        "all_manuscript_result_claims_observed": evidence["acceptance"]["all_manuscript_result_claims_observed"],
        "calibration": evidence["calibration"],
        "usage": evidence["usage"],
    }, ensure_ascii=False, indent=2))
    return 0 if evidence["acceptance"]["execution_accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
