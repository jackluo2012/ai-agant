#!/usr/bin/env python3
"""失败即拒绝（fail-closed）的留痕证据校验器。

验证 validation/runs 下保留的实验 10-3 运行证据：重算全部哈希、独立规范化
原始工具调用参数、检查隐私脱敏与验收门禁。历史运行（原书仓库时期）由
Volcengine ARK 端点产生；本工作区迁移后的新运行由统一 LLM 客户端产生，
因此 provider/endpoint 只做非空校验。历史证据绑定的源码哈希属于原书源码，
可用 --skip-source-hashes 做只读参考校验。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

TOOL_NAME = "initiate_phone_call_agent"
INPUT_NAMES = {"experiment_input.json"}
ARTIFACT_NAMES = {
    "acceptance_report.json",
    "decision.json",
    "form_submission_receipt.json",
    "message_timeline.json",
    "raw_decision_request.json",
    "raw_decision_response.json",
    "validation_report.json",
}
SOURCE_NAMES = {
    "browser.py",
    "bus.py",
    "decision.py",
    "demo.py",
    "models.py",
    "orchestration.py",
    "run_acceptance.py",
    "validate_acceptance.py",
    "voice.py",
    "webrtc_channel.py",
}
CREDENTIAL_PATTERN = re.compile(
    r"(?i)(?:sk-[A-Za-z0-9_-]{12,}|gho_[A-Za-z0-9_-]{12,}|"
    r"github_pat_[A-Za-z0-9_-]{12,}|authorization.{0,16}bearer\s+[A-Za-z0-9._-]{12,})"
)


class ValidationFailure(RuntimeError):
    """当留痕证据无法证明其声明时抛出。"""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationFailure(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationFailure(f"无法读取 JSON 证据 {path.name}: {exc}") from exc
    _require(isinstance(value, dict), f"{path.name} 必须是 JSON object")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValidationFailure(f"无法计算 {path} 的哈希: {exc}") from exc


def _validate_hash_map(
    *,
    expected_names: set[str],
    hashes: Any,
    base: Path,
    label: str,
) -> None:
    """校验 manifest 中一组哈希的文件名与哈希值都完全一致。"""
    _require(isinstance(hashes, dict), f"manifest 的 {label} 必须是 object")
    names = set(hashes)
    _require(names == expected_names, f"manifest {label} 的文件名不一致: {sorted(names)}")
    for name, expected in hashes.items():
        _require(
            isinstance(expected, str) and len(expected) == 64, f"{name} 的 {label} 哈希格式非法"
        )
        _require(_sha256(base / name) == expected, f"{name} 的 {label} 哈希不匹配")


def _tool_call(response: dict[str, Any]) -> dict[str, Any]:
    """从原始响应中提取唯一的工具调用，并校验其结构。"""
    choices = response.get("choices")
    _require(isinstance(choices, list) and len(choices) == 1, "原始响应必须只有一个 choice")
    choice = choices[0]
    _require(
        choice.get("finish_reason") == "tool_calls", "原始响应未以 tool_calls 结束"
    )
    message = choice.get("message", {})
    calls = message.get("tool_calls")
    _require(isinstance(calls, list) and len(calls) == 1, "原始响应必须只有一个工具调用")
    call = calls[0]
    _require(call.get("type") == "function", "原始响应的工具调用必须是 function 类型")
    function = call.get("function", {})
    _require(function.get("name") == TOOL_NAME, "原始响应选择了错误的工具")
    return function


def _normalized_required_info(
    raw_arguments: dict[str, Any], decision: dict[str, Any]
) -> list[dict[str, Any]]:
    """把原始工具参数独立规范化，作为与 decision.json 对比的基准。"""
    discovered = decision.get("discovered_fields")
    _require(isinstance(discovered, list), "规范化 decision 缺少 discovered_fields")
    by_name = {str(field.get("name", "")): field for field in discovered}
    by_label = {str(field.get("label", "")).casefold(): field for field in discovered}
    known = set(decision.get("known_fields", []))
    normalized = []
    for item in raw_arguments.get("required_info", []):
        _require(isinstance(item, dict), "原始 required_info 的条目必须是 object")
        candidate = by_name.get(str(item.get("name", ""))) or by_label.get(
            str(item.get("label", "")).casefold()
        )
        _require(candidate is not None, "原始工具参数引用了未知字段")
        if candidate["name"] not in known and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def validate_run(
    run_dir: Path,
    *,
    source_root: Path | None = None,
    require_validation_report: bool = True,
    verify_source_hashes: bool = True,
) -> dict[str, Any]:
    """校验一次留痕运行并返回确定性的校验报告。

    Args:
        run_dir: 运行证据目录
        source_root: 源码根目录（用于 source_sha256 校验）
        require_validation_report: 是否要求已存在的 validation_report.json 与重算结果一致
        verify_source_hashes: 是否校验 source_sha256；历史证据绑定原书源码，
            在迁移后的工作区做只读参考校验时应传入 False

    Returns:
        校验报告字典
    """
    run_dir = run_dir.resolve()
    source_root = (source_root or Path(__file__).parent).resolve()
    manifest = _load_json(run_dir / "manifest.json")
    _require(manifest.get("schema_version") == 2, "manifest 的 schema_version 必须是 2")
    _require(manifest.get("experiment") == "10-3", "manifest 的 experiment 必须是 10-3")

    artifact_names = (
        ARTIFACT_NAMES if require_validation_report else ARTIFACT_NAMES - {"validation_report.json"}
    )
    expected_run_names = {"manifest.json"} | INPUT_NAMES | artifact_names
    actual_run_names = {path.name for path in run_dir.iterdir()}
    _require(
        actual_run_names == expected_run_names,
        f"留痕运行的文件集合不一致: {sorted(actual_run_names)}",
    )
    # 输入与产物哈希必须逐一重算匹配
    input_hashes = manifest.get("input_sha256")
    _validate_hash_map(
        expected_names=INPUT_NAMES,
        hashes=input_hashes,
        base=run_dir,
        label="input_sha256",
    )
    _validate_hash_map(
        expected_names=artifact_names,
        hashes=manifest.get("artifact_sha256"),
        base=run_dir,
        label="artifact_sha256",
    )
    source_hashes = manifest.get("source_sha256")
    _require(isinstance(source_hashes, dict), "manifest 的 source_sha256 必须是 object")
    _require(set(source_hashes) == SOURCE_NAMES, "manifest source_sha256 的文件名不一致")
    if verify_source_hashes:
        # 新工作区运行：源码哈希必须与当前源码一致
        for name, expected in source_hashes.items():
            _require(_sha256(source_root / name) == expected, f"{name} 的 source_sha256 不匹配")
    _require(
        re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("git_head_at_run", ""))) is not None,
        "manifest 的 git_head_at_run 非法",
    )

    experiment_input = _load_json(run_dir / "experiment_input.json")
    raw_request = _load_json(run_dir / "raw_decision_request.json")
    raw_response = _load_json(run_dir / "raw_decision_response.json")
    decision = _load_json(run_dir / "decision.json")
    acceptance = _load_json(run_dir / "acceptance_report.json")
    form_receipt = _load_json(run_dir / "form_submission_receipt.json")
    timeline = json.loads((run_dir / "message_timeline.json").read_text(encoding="utf-8"))

    # provider/endpoint 通用校验：历史证据为 Volcengine ARK，
    # 迁移后的新运行由统一 LLM 客户端按 .env 配置产生
    _require(bool(raw_request.get("provider")), "原始请求缺少 provider 标识")
    _require(bool(raw_request.get("endpoint")), "原始请求缺少 endpoint 标识")
    _require(
        raw_request.get("credential_fields_retained") == [],
        "原始请求保留了凭据字段",
    )
    request = raw_request.get("request", {})
    _require(request.get("tool_choice") == "auto", "原始请求未使用 tool_choice=auto")
    tools = request.get("tools")
    _require(
        isinstance(tools, list) and len(tools) == 1, "原始请求必须只暴露一个可选工具"
    )
    _require(
        tools[0].get("function", {}).get("name") == TOOL_NAME, "原始请求的工具 schema 不一致"
    )

    _require(bool(raw_response.get("provider")), "原始响应缺少 provider 标识")
    _require(bool(decision.get("provider")), "规范化 decision 缺少 provider 标识")
    latency = raw_response.get("latency_seconds")
    _require(
        isinstance(latency, (int, float)) and latency > 0, "原始响应缺少正的延迟数据"
    )
    response = raw_response.get("response", {})
    _require(
        response.get("id") == decision.get("provider_response_id"),
        "响应 ID 与 decision 不一致",
    )
    _require(request.get("model") == decision.get("model"), "请求模型与 decision 不一致")
    _require(response.get("model") == decision.get("model"), "响应模型与 decision 不一致")
    usage = response.get("usage", {})
    normalized_usage = {
        key: usage[key]
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if key in usage
    }
    _require(
        normalized_usage == decision.get("provider_usage"), "响应 usage 与 decision 不一致"
    )

    function = _tool_call(response)
    try:
        raw_arguments = json.loads(function["arguments"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValidationFailure("原始工具调用参数不是合法 JSON") from exc
    _require(isinstance(raw_arguments, dict), "原始工具调用参数必须是 object")
    _require(
        set(raw_arguments) == {"purpose", "required_info"},
        "原始工具调用参数包含意外字段",
    )
    _require(isinstance(raw_arguments["required_info"], list), "原始 required_info 必须是列表")
    _require(decision.get("tool_called") == TOOL_NAME, "规范化 decision 记录的工具不正确")
    _require(
        raw_arguments.get("purpose") == decision.get("purpose"), "原始 purpose 与 decision 不一致"
    )
    _require(
        _normalized_required_info(raw_arguments, decision) == decision.get("required_info"),
        "原始工具调用参数规范化后与 decision.json 不完全一致",
    )

    messages = request.get("messages")
    _require(
        isinstance(messages, list) and len(messages) == 2, "原始请求的 messages 不完整"
    )
    try:
        user_observation = json.loads(messages[1]["content"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValidationFailure("原始请求的用户观察不合法") from exc
    _require(
        user_observation.get("page_url") == experiment_input.get("page_url"),
        "输入的页面 URL 不一致",
    )
    visible_decision_fields = [
        {
            "name": field["name"],
            "label": field["label"],
            "type": field["input_type"],
            "required": field["required"],
            "format_hint": field["format_hint"],
            "options": field["options"],
        }
        for field in decision["discovered_fields"]
    ]
    _require(
        user_observation.get("form_fields") == visible_decision_fields,
        "原始页面观察不一致",
    )
    _require(
        experiment_input.get("form_html_sha256")
        == hashlib.sha256(experiment_input.get("form_html", "").encode("utf-8")).hexdigest(),
        "输入表单 HTML 哈希不一致",
    )

    # 验收门禁与隐私声明
    _require(acceptance.get("overall_status") == "pass", "验收状态不是 pass")
    gates = acceptance.get("gates", {})
    _require(
        gates and all(item.get("status") == "pass" for item in gates.values()),
        "存在未通过的验收门禁",
    )
    _require(
        manifest.get("acceptance")
        == {
            "overall_status": "pass",
            "gate_count": len(gates),
            "passed_gate_count": len(gates),
        },
        "manifest 的验收摘要不一致",
    )
    if require_validation_report:
        _require(
            manifest.get("retained_evidence_validation") == "pass",
            "manifest 的留痕证据状态不是 pass",
        )
    _require(isinstance(timeline, list), "消息时序必须是列表")
    collected = [row for row in timeline if row.get("type") == "info_collected"]
    _require(collected, "消息时序中没有已收集字段")
    _require(
        all(row.get("payload", {}).get("value") == "<redacted>" for row in collected),
        "参与者值未被脱敏",
    )
    _require(
        acceptance.get("webrtc_receipt", {}).get("raw_audio_retained") is False,
        "保留了原始音频",
    )
    _require(
        acceptance.get("webrtc_receipt", {}).get("transcripts_retained") is False,
        "保留了转录文本",
    )
    _require(
        experiment_input.get("participant_values_retained") is False, "输入声明保留了参与者值"
    )
    _require(form_receipt.get("raw_values_retained") is False, "表单回执保留了原始值")
    # 全部留痕文件做一次凭据扫描
    retained_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(run_dir.iterdir()) if path.is_file()
    )
    _require(
        not CREDENTIAL_PATTERN.search(retained_text), "留痕证据中包含凭据"
    )

    # checks 键名是 schema v1 的固定标识，与已保留的 validation_report.json 保持一致
    result = {
        "schema_version": 1,
        "experiment": "10-3",
        "status": "pass",
        "checks": {
            "source_hashes": "pass",
            "artifact_hashes": "pass",
            "input_hashes": "pass",
            "raw_ark_request_tool_choice_auto": "pass",
            "raw_ark_response_metadata": "pass",
            "raw_arguments_normalize_to_decision": "pass",
            "participant_privacy": "pass",
            "acceptance_gates": "pass",
        },
    }
    if verify_source_hashes is False:
        result["checks"]["source_hashes"] = "skipped"
    if require_validation_report:
        retained = _load_json(run_dir / "validation_report.json")
        # 参考模式（源码哈希跳过）下，历史报告的 source_hashes 为 "pass" 而重算
        # 结果诚实地标记为 "skipped"；除该键外其余内容必须完全一致。
        def _comparable(report: dict[str, Any]) -> tuple:
            return (
                report.get("schema_version"),
                report.get("experiment"),
                report.get("status"),
                {k: v for k, v in report.get("checks", {}).items() if k != "source_hashes"},
            )

        _require(
            _comparable(retained) == _comparable(result),
            "已保留的校验报告与重算结果不一致",
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).parent)
    parser.add_argument(
        "--skip-source-hashes",
        action="store_true",
        help="跳过源码哈希校验（用于原书仓库历史证据的只读参考校验）",
    )
    args = parser.parse_args()
    report = validate_run(
        args.run_dir,
        source_root=args.source_root,
        verify_source_hashes=not args.skip_source_hashes,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
