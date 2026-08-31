#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立校验器：从验收报告中重新计算「工具调用 → 音频 → ASR」边界是否成立。

本脚本与 demo.py 内置的校验互为独立复核：它只读取落盘的报告 JSON 与语音
事件轨迹，重新逐条验证每次 LLM 工具调用都配有同座位的 TTS 音频与事务内的
ASR 转写、音频哈希前后一致、提供商回执唯一，从而确认模拟用户的动作没有被
语音边界静默改变。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

# 添加项目根目录到路径（用于导入 werewolf 包）
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from werewolf.human import HumanPlayerAgent  # noqa: E402


def validate(report_path: Path) -> dict:
    """对一份验收报告做严格的音频/动作边界校验，返回校验结果字典。"""
    raw = report_path.read_bytes()
    report = json.loads(raw)
    events = report.get("voice_events", [])
    errors = []
    checked = 0
    seen_sequences = set()
    seen_request_ids = set()
    seen_provider_ids = set()
    simulator_asr_count = sum(
        isinstance(event, dict) and event.get("type") == "simulator_asr"
        for event in events
    ) if isinstance(events, list) else 0
    simulator_tool_count = 0

    if not isinstance(events, list):
        errors.append("voice_events 必须是数组")
        events = []

    # 轨迹必须是只追加的序列。拒绝重复/乱序的 sequence，防止后一个事件
    # 被意外配对到前一个动作上。
    previous_sequence = 0
    for event in events:
        if not isinstance(event, dict):
            errors.append("每个语音事件都必须是对象")
            continue
        sequence = event.get("sequence")
        if isinstance(sequence, int) and sequence in seen_sequences:
            errors.append(f"语音事件 sequence 重复：{sequence}")
        if not isinstance(sequence, int) or sequence <= previous_sequence:
            errors.append(f"语音事件 sequence 未严格递增：{sequence!r}")
        if isinstance(sequence, int):
            seen_sequences.add(sequence)
            previous_sequence = max(previous_sequence, sequence)

    for index, event in enumerate(events):
        if not isinstance(event, dict):
            continue
        if event.get("type") != "simulator_llm_tool":
            continue
        checked += 1
        simulator_tool_count += 1
        # 工具调用必须带提供商回执 ID，且全局唯一（防伪造/防重放）
        tool_request_id = event.get("response_id") or event.get("request_id")
        if not isinstance(tool_request_id, str) or not tool_request_id.strip():
            errors.append(f"工具事件 {event.get('sequence')} 缺少提供商 response_id")
        elif tool_request_id in seen_provider_ids:
            errors.append(f"工具提供商 response_id 重复：{tool_request_id}")
        else:
            seen_provider_ids.add(tool_request_id)
        seat = event.get("seat")
        if not isinstance(seat, str) or not re.fullmatch(r"P\d+", seat):
            errors.append(f"工具事件 {event.get('sequence')} 的座位非法")
        # 只有本次动作的相邻事务内的事件才可用。旧版校验器一路搜到轨迹末尾，
        # 缺失的 ASR 可能悄悄借用另一个回合的转写。
        transaction = []
        for item in events[index + 1:]:
            if not isinstance(item, dict):
                errors.append(f"工具事件 {event.get('sequence')} 的事务中含非对象事件")
                continue
            if item.get("type") == "simulator_llm_tool":
                break
            transaction.append(item)
        tts = next((item for item in transaction
                    if item.get("type") == "tts_ready" and item.get("speaker") == seat), None)
        following = next((item for item in transaction
                          if item.get("type") == "simulator_asr"), None)
        if tts is None:
            errors.append(f"工具事件 {event.get('sequence')} 没有同座位的 TTS")
        if following is None:
            errors.append(f"工具事件 {event.get('sequence')} 的事务内没有 simulator_asr")
            continue
        if tts is not None:
            # 先合成、后识别；且 ASR 听到的哈希必须等于 TTS 产出的哈希
            if transaction.index(tts) > transaction.index(following):
                errors.append(f"工具事件 {event.get('sequence')} 的 ASR 发生在 TTS 之前")
            audio_hash = tts.get("audio_sha256")
            source_hash = following.get("source_audio_sha256")
            if not isinstance(audio_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", audio_hash):
                errors.append(f"工具事件 {event.get('sequence')} 的 TTS 音频哈希非法")
            if source_hash != audio_hash:
                errors.append(f"工具事件 {event.get('sequence')} 的 ASR 源哈希与 TTS 不一致")
            if not isinstance(tts.get("audio_bytes"), int) or tts["audio_bytes"] <= 0:
                errors.append(f"工具事件 {event.get('sequence')} 的 TTS 音频为空")
        request_id = following.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            errors.append(f"工具事件 {event.get('sequence')} 的 ASR 缺少 request_id")
        elif request_id in seen_request_ids:
            errors.append(f"ASR request_id 重复：{request_id}")
        else:
            seen_request_ids.add(request_id)
            if request_id in seen_provider_ids:
                errors.append(f"提供商 response_id 被 ASR 复用：{request_id}")
            seen_provider_ids.add(request_id)
        arguments = event.get("arguments") or {}
        if event.get("tool") == "speak_publicly":
            # 公开发言只要转写非空即可（发言内容不需要与目标解析对齐）
            if not str(following.get("transcript", "")).strip():
                errors.append(f"发言工具事件 {event.get('sequence')} 的 ASR 转写为空")
            continue
        target = arguments.get("target")
        transcript = str(following.get("transcript", ""))
        if target == "none":
            # 选择弃票时，转写必须包含明确的弃票表述
            if not HumanPlayerAgent._explicit_none(transcript):
                errors.append(
                    f"工具事件 {event.get('sequence')} 选择了 none，"
                    f"但 ASR 不是明确的弃票表述：{transcript!r}"
                )
        elif target and target not in transcript.replace(" ", ""):
            # 英文数字序数的转写同样合法：用生产解析器、以报告花名册为候选集复核
            try:
                player_count = int(report["players"])
            except (KeyError, TypeError, ValueError):
                player_count = 0
                errors.append("报告的 players 字段必须是整数")
            candidates = [f"P{number}" for number in range(1, player_count + 1)]
            parsed = HumanPlayerAgent._spoken_target(transcript, candidates, False)
            if parsed != target:
                errors.append(
                    f"工具事件 {event.get('sequence')} 选择了 {target}，"
                    f"但 ASR 解析出 {parsed}"
                )
    # 报告中的统计字段必须与轨迹逐条对账
    if simulator_tool_count != report.get("simulator_llm_tool_calls", simulator_tool_count):
        errors.append("报告的 simulator_llm_tool_calls 与轨迹不一致")
    if simulator_asr_count != report.get("simulator_audio_roundtrips", simulator_asr_count):
        errors.append("报告的 simulator_audio_roundtrips 与轨迹不一致")
    if any(isinstance(event, dict) and event.get("type") == "simulator_action_mismatch"
           for event in events):
        errors.append("轨迹中存在 simulator_action_mismatch")
    return {
        "schema_version": 1,
        "source_report": str(report_path),
        "source_report_sha256": hashlib.sha256(raw).hexdigest(),
        "simulator_tool_events_checked": checked,
        "strict_audio_action_boundary": "pass" if checked and not errors else "fail",
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="独立校验模拟用户运行的音频/动作边界（只读报告，不发任何网络请求）")
    parser.add_argument("report", type=Path, help="验收报告 JSON 路径")
    parser.add_argument("--output", type=Path, help="校验结果输出路径（可选）")
    args = parser.parse_args()
    result = validate(args.report)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["strict_audio_action_boundary"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
