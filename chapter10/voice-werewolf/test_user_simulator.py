# -*- coding: utf-8 -*-
"""用户模拟器（SimulatedUserPlayerAgent / SimulatedVoiceSession）的单元测试。"""

import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import demo
from werewolf import agent as agent_module
from werewolf.game import Judge, create_players
from werewolf.roles import Role
from werewolf.agent import PlayerAgent
from werewolf.simulator import SimulatedUserPlayerAgent, SimulatedVoiceSession


class FakeVoice:
    """测试替身：记录发言与事件，按脚本回放 ASR 转写文本。"""

    def __init__(self, transcripts=None):
        self.events = []
        self.transcripts = iter(transcripts or [])
        self.spoken = []

    def say(self, speaker, text, round_no, allow_barge_in=False):
        self.spoken.append((speaker, text, round_no))

    def record_llm_decision(self, **data):
        self.events.append({"type": "simulator_llm_tool", **data})

    def roundtrip_user(self, speaker, text, round_no):
        self.spoken.append((speaker, text, round_no))
        return next(self.transcripts)

    def _event(self, type_, **data):
        self.events.append({"type": type_, **data})


def fake_llm_client():
    """构造一个最小化的客户端替身（仅需 model_name 属性）。"""
    return SimpleNamespace(model_name="test-model")


def tool_response(name, arguments):
    call = SimpleNamespace(
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments, ensure_ascii=False))
    )
    message = SimpleNamespace(tool_calls=[call])
    return SimpleNamespace(
        id="response-real-shape",
        model="provider-model",
        usage=SimpleNamespace(model_dump=lambda: {"prompt_tokens": 10, "completion_tokens": 3}),
        choices=[SimpleNamespace(message=message)],
    )


def test_simulated_user_is_one_randomized_protected_user_seat():
    voice = FakeVoice()
    players = create_players(
        seed=42,
        players=7,
        wolves=2,
        simulated_user_seat=1,
        voice=voice,
    )
    assert sum(isinstance(player, SimulatedUserPlayerAgent) for player in players) == 1
    assert sum(getattr(player, "is_user", False) for player in players) == 1
    assert players[0].role in set(Role)

    judge = Judge(players, seed=42)
    judge.assign_identities()
    assert any("您的身份" in text for _, text, _ in voice.spoken)


def test_simulator_uses_private_context_tool_and_only_asr_speech(monkeypatch):
    voice = FakeVoice(transcripts=["ASR 后的公开发言"])
    player = SimulatedUserPlayerAgent("P1", Role.VILLAGER, voice, model="test/model")
    player.observe("仅 P1 可见的记忆")
    captured = {}
    response = tool_response("speak_publicly", {"utterance": "LLM 原始公开发言"})
    monkeypatch.setattr(agent_module, "get_client", fake_llm_client)

    def fake_create(_client, **kwargs):
        captured.update(kwargs)
        return response

    monkeypatch.setattr(agent_module, "_safe_create", fake_create)

    speech = player.speak(["P1", "P2"])

    # 游戏只应消费 ASR 转写文本，而非 LLM 的原始发言
    assert speech == "ASR 后的公开发言"
    assert "仅 P1 可见的记忆" in captured["messages"][1]["content"]
    assert captured["tool_choice"]["function"]["name"] == "speak_publicly"
    assert captured["tools"][0]["function"]["parameters"]["additionalProperties"] is False
    assert voice.spoken[-1][1] == "LLM 原始公开发言"
    assert voice.events[0]["tool"] == "speak_publicly"


def test_simulator_fails_closed_when_asr_changes_selected_action(monkeypatch):
    # ASR 把「三号」误听成「四号」：语音边界改变了动作 → 必须硬失败
    voice = FakeVoice(transcripts=["我选择四号玩家。"])
    player = SimulatedUserPlayerAgent("P1", Role.VILLAGER, voice)
    response = tool_response("choose_player", {"target": "P2", "reason": "公开证据"})
    monkeypatch.setattr(agent_module, "get_client", fake_llm_client)
    monkeypatch.setattr(agent_module, "_safe_create", lambda _client, **kwargs: response)

    with pytest.raises(RuntimeError, match="语音边界改变了模拟器的动作"):
        player.vote(["P2", "P3"], ["P1", "P2", "P3"])

    mismatch = voice.events[-1]
    assert mismatch["type"] == "simulator_action_mismatch"
    assert mismatch["tool_target"] == "P2"
    assert mismatch["parsed_target"] == "P4"


def test_simulator_fails_closed_when_abstention_is_not_explicit_in_asr(monkeypatch):
    # 工具选择了弃票，但转写文本里没有明确的弃票表述 → 必须硬失败
    voice = FakeVoice(transcripts=["我选 P2。"])
    player = SimulatedUserPlayerAgent("P1", Role.VILLAGER, voice)
    response = tool_response("choose_player", {"target": "none", "reason": "证据不足"})
    monkeypatch.setattr(agent_module, "get_client", fake_llm_client)
    monkeypatch.setattr(agent_module, "_safe_create", lambda _client, **kwargs: response)

    with pytest.raises(RuntimeError, match="语音边界改变了模拟器的动作"):
        player.vote(["P2", "P3"], ["P1", "P2", "P3"])

    assert voice.spoken[-1][1] == "我选择弃票。"
    assert voice.events[-1]["type"] == "simulator_action_mismatch"


def test_judge_retains_llm_decision_reason_in_action_evidence(monkeypatch):
    voice = FakeVoice(transcripts=["我选择二号玩家。"])
    simulator = SimulatedUserPlayerAgent("P1", Role.VILLAGER, voice)
    response = tool_response(
        "choose_player", {"target": "P2", "reason": "P2 与公开投票记录矛盾"}
    )
    monkeypatch.setattr(agent_module, "get_client", fake_llm_client)
    monkeypatch.setattr(agent_module, "_safe_create", lambda _client, **kwargs: response)
    target = simulator.vote(["P2"], ["P1", "P2"])
    record = Judge._decision_record(
        simulator, round=1, phase="vote", actor="P1", role="村民",
        action="vote", target=target,
    )
    # 模型给出的决策理由应保留进证据记录，且随后从玩家状态中清空
    assert record["reason"] == "P2 与公开投票记录矛盾"
    assert simulator.last_decision_reason is None


def test_good_faction_vote_prompt_prioritizes_uncontested_seer_evidence(monkeypatch):
    player = PlayerAgent("P7", Role.VILLAGER)
    captured = {}

    def fake_chat(instruction, players, max_tokens, json_mode=False):
        captured["instruction"] = instruction
        return '{"target": "P5", "reason": "P4 is uncontested and checked P5 as a wolf"}'

    monkeypatch.setattr(player, "_chat", fake_chat)
    assert player.vote(["P4", "P5"], ["P4", "P5", "P7"]) == "P5"
    assert "不得投该声明者" in captured["instruction"]
    assert "被查杀者仅仅否认并不构成" in captured["instruction"]


def test_reasoning_model_empty_content_retries_with_larger_bounded_budget(monkeypatch):
    player = PlayerAgent("P7", Role.VILLAGER)
    calls = []
    responses = iter([
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=""))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="visible speech"))]),
    ])
    monkeypatch.setattr(agent_module, "get_client", fake_llm_client)

    def fake_create(_client, **kwargs):
        calls.append(kwargs)
        return next(responses)

    monkeypatch.setattr(agent_module, "_safe_create", fake_create)
    assert player._chat("speak", ["P7"], max_tokens=180) == "visible speech"
    # 第一次请求使用下限兜底预算（512），空内容重试时扩大到 2048
    assert calls[0]["max_tokens"] == 512
    assert calls[1]["max_tokens"] == 2048


def test_simulator_vote_prompt_uses_the_same_evidence_priority(monkeypatch):
    voice = FakeVoice(transcripts=["我选择五号玩家。"])
    player = SimulatedUserPlayerAgent("P1", Role.VILLAGER, voice)
    captured = {}
    response = tool_response(
        "choose_player", {"target": "P5", "reason": "P4 is the only Seer and checked P5"}
    )
    monkeypatch.setattr(agent_module, "get_client", fake_llm_client)

    def fake_create(_client, **kwargs):
        captured.update(kwargs)
        return response

    monkeypatch.setattr(agent_module, "_safe_create", fake_create)
    assert player.vote(["P4", "P5"], ["P1", "P4", "P5"]) == "P5"
    instruction = captured["messages"][1]["content"]
    assert "不得投该声明者" in instruction
    assert "被查杀者仅仅否认不构成" in instruction


def test_local_speech_falls_back_to_macos_say(monkeypatch, tmp_path):
    """local 语音回环：无 espeak 时回退到 macOS say 合成真实波形。"""
    from werewolf import simulator as simulator_module

    paths = {"espeak-ng": None, "espeak": None, "say": "/usr/bin/say", "ffmpeg": "/opt/bin/ffmpeg"}
    monkeypatch.setattr(simulator_module.shutil, "which", lambda name: paths.get(name))
    # 构造会话需要统一客户端，这里注入替身避免真实网络配置
    monkeypatch.setattr(simulator_module, "get_llm_client", fake_llm_client)

    def fake_run(command, **kwargs):
        if command[0] == "/usr/bin/say":
            output = command[command.index("-o") + 1]
        else:
            output = command[-1]
        from pathlib import Path
        Path(output).write_bytes(b"real-audio-shaped-bytes")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(simulator_module.subprocess, "run", fake_run)
    session = SimulatedVoiceSession(str(tmp_path), provider="local")
    path = session._synthesize("P1", "我选择四号玩家。", 1)
    assert path.read_bytes() == b"real-audio-shaped-bytes"
    assert session.events[0]["model"] == "macos-say-Tingting"


def test_simulated_user_cli_needs_no_human_consent(monkeypatch):
    # --simulate-user 是自动端到端路径，不需要真人知情同意标志
    monkeypatch.setenv("API_KEY", "configured-for-test")
    monkeypatch.setattr(sys, "argv", ["demo.py", "--simulate-user"])
    with patch("demo.run_game", return_value=True) as run_game:
        demo.main()
    assert run_game.call_args.args[0].simulate_user is True
    assert run_game.call_args.args[0].confirm_human_consent is False
