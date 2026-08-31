# -*- coding: utf-8 -*-
"""LLM 驱动的用户模拟器：真实的语音往返（TTS → 音频 → ASR）。

这个模拟器刻意**不是一个普通的 AI 玩家**。它占据与 HumanPlayerAgent 相同的
受保护用户座位，只接收该座位的私有记忆。每一轮都必须由一个独立的 LLM 通过
工具调用给出合法动作；选定的发言文本先被合成为真实音频，游戏只消费 ASR 的
转写文本、绝不直接使用原始文本——这样 ASR 的误识别就成为可观测的一环，
而不是被静默绕过语音边界。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

# 添加项目根目录到路径（用于导入统一的 llm.client 模块）
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from llm.client import get_llm_client
except ImportError:
    get_llm_client = None

from . import agent as agent_module
from .agent import PlayerAgent
from .human import HumanPlayerAgent
from .roles import Role


def _usage_dict(value):
    """把 SDK 的 usage 对象转成可 JSON 序列化的字典（兼容多种返回形态）。"""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return None


class SimulatedVoiceSession:
    """合成用户的「无头」语音传输层。

    两种语音回环方式：
    - ``api``：用统一 LLM 客户端（项目根目录 .env 配置）的托管 TTS 与 ASR 接口。
    - ``local``：用本地系统合成器（espeak / macOS say）生成真实波形，再用统一
      客户端的多模态模型完成 ASR。
    ``auto`` 自动选择：配置可用时优先 ``api``，否则回退 ``local``。
    无论哪种方式，LLM 用户的文本都必须经过一个真实的音频文件和 ASR 才会进入
    游戏，保证语音边界是真实存在的。
    """

    def __init__(self, out_dir: str, *, provider: str = "auto"):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.events = []
        self._sequence = 0
        requested = provider.casefold()
        if requested == "auto":
            # 自动模式：优先纯 API 回环；本机合成器可用时也可回退 local
            requested = "api"
        if requested not in {"api", "local"}:
            raise ValueError("模拟用户语音回环方式必须是 auto、api 或 local")
        self.provider = requested
        # 统一客户端：文本决策与音频接口共用同一份 .env 配置
        if get_llm_client is None:
            raise RuntimeError(
                "无法导入统一 LLM 客户端 llm.client。请从项目根目录运行本实验。"
            )
        self.client = get_llm_client()
        self.espeak = None
        self.system_say = None
        self.ffmpeg = None
        if requested == "local":
            # local 模式依赖本机合成器与 ffmpeg（重采样为 24kHz 单声道 wav）
            self.espeak = shutil.which("espeak-ng") or shutil.which("espeak")
            self.system_say = shutil.which("say")
            self.ffmpeg = shutil.which("ffmpeg")
            if not (self.espeak or self.system_say) or not self.ffmpeg:
                raise RuntimeError(
                    "local 语音回环需要 espeak（Linux）或 say（macOS），并且需要 ffmpeg"
                )

    def _event(self, type_: str, **data):
        """记录一条语音事件轨迹并落盘（供赛后独立校验器复核）。"""
        self._sequence += 1
        event = {
            "sequence": self._sequence,
            "monotonic": time.monotonic(),
            "wall_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "type": type_,
            **data,
        }
        self.events.append(event)
        (self.out_dir / "simulator_voice_trace.json").write_text(
            json.dumps(self.events, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return event

    def record_llm_decision(self, **data):
        """记录模拟用户的一次 LLM 工具调用决策（进入语音轨迹）。"""
        self._event("simulator_llm_tool", **data)

    def _synthesize(self, speaker: str, text: str, round_no: int) -> Path:
        """把一段发言合成为音频文件（api：托管 TTS；local：本机合成器）。"""
        if not text.strip():
            raise ValueError("拒绝合成空发言")
        started = time.monotonic()
        stem = f"r{round_no}_{speaker}_{self._sequence + 1}"
        request_id = None
        model = None
        if self.provider == "api":
            path = self.out_dir / f"{stem}.mp3"
            model = os.getenv("OPENAI_TTS_MODEL", "tts-1")
            response = self.client.audio.speech.create(
                model=model,
                voice=os.getenv("OPENAI_TTS_VOICE", "coral"),
                input=text,
                response_format="mp3",
            )
            path.write_bytes(response.content)
            request_id = getattr(response, "_request_id", None)
            provider = "统一客户端音频 API"
        else:
            path = self.out_dir / f"{stem}.wav"
            with tempfile.TemporaryDirectory(prefix="werewolf-simulator-tts-") as directory:
                if self.espeak:
                    voice = os.getenv("SIMULATOR_ESPEAK_VOICE", "cmn")
                    model = f"espeak-{voice}"
                    source = Path(directory) / "speech.wav"
                    command = [
                        self.espeak,
                        "-v", voice,
                        "-s", os.getenv("SIMULATOR_ESPEAK_SPEED", "145"),
                        "-w", str(source),
                        text,
                    ]
                else:
                    voice = os.getenv("SIMULATOR_SAY_VOICE", "Tingting")
                    model = f"macos-say-{voice}"
                    source = Path(directory) / "speech.aiff"
                    command = [self.system_say, "-v", voice, "-o", str(source), text]
                # 先用本机合成器生成源音频，再用 ffmpeg 重采样为 24kHz 单声道
                subprocess.run(command, check=True, capture_output=True)
                subprocess.run(
                    [self.ffmpeg, "-nostdin", "-loglevel", "error", "-y", "-i",
                     str(source), "-ac", "1", "-ar", "24000", str(path)],
                    check=True,
                    capture_output=True,
                )
            provider = "本机合成器"
        content = path.read_bytes()
        if not content:
            raise RuntimeError("语音合成器返回了空音频")
        self._event(
            "tts_ready",
            speaker=speaker,
            provider=provider,
            model=model,
            request_id=request_id,
            latency_seconds=round(time.monotonic() - started, 3),
            file=str(path),
            audio_bytes=len(content),
            audio_sha256=hashlib.sha256(content).hexdigest(),
        )
        return path

    def _transcribe(self, path: Path) -> str:
        """把音频送往 ASR：api 走专用转写接口，local 走多模态模型听音频。"""
        started = time.monotonic()
        request_id = None
        usage = None
        if self.provider == "api":
            model = os.getenv("OPENAI_ASR_MODEL", "whisper-1")
            with path.open("rb") as audio:
                response = self.client.audio.transcriptions.create(
                    model=model,
                    file=audio,
                    language=os.getenv("VOICE_LANGUAGE", "zh"),
                )
            transcript = response.text.strip()
            request_id = getattr(response, "_request_id", None)
            provider = "统一客户端音频 API"
        else:
            # local 模式：把 wav 以 base64 塞进多模态消息，由模型直接听写
            model = os.getenv("SIMULATOR_ASR_MODEL")
            if not model:
                raise RuntimeError(
                    "local 语音回环需要设置 SIMULATOR_ASR_MODEL"
                    "（一个支持音频输入的多模态模型名）"
                )
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": (
                        "请逐字转写这段狼人杀游戏发言，只返回转写文本本身，"
                        "不要加任何标签、引号、解释或 Markdown。"
                        "保留 P1 之类的座位编号和中文玩家编号说法。"
                    )},
                    {"type": "input_audio", "input_audio": {
                        "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                        "format": "wav",
                    }},
                ]}],
                temperature=0,
                max_tokens=512,
            )
            transcript = (response.choices[0].message.content or "").strip()
            request_id = getattr(response, "id", None)
            usage = _usage_dict(getattr(response, "usage", None))
            provider = "统一客户端多模态音频 API"
        if not transcript:
            raise RuntimeError("ASR 返回了空转写")
        self._event(
            "simulator_asr",
            provider=provider,
            model=model,
            request_id=request_id,
            usage=usage,
            latency_seconds=round(time.monotonic() - started, 3),
            source_audio_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            transcript=transcript,
        )
        return transcript

    def roundtrip_user(self, speaker: str, text: str, round_no: int) -> str:
        """完整的用户语音回环：合成音频 → ASR 转写。游戏只见转写文本。"""
        path = self._synthesize(speaker, text, round_no)
        return self._transcribe(path)

    def say(self, speaker: str, text: str, round_no: int, *, allow_barge_in: bool = False):
        """合成但不转写（用于模拟用户座位的单程播报）。"""
        self._synthesize(speaker, text, round_no)
        return None

    def synth(self, speaker: str, text: str, round_no: int):
        return self.say(speaker, text, round_no)


class SimulatedUserPlayerAgent(PlayerAgent):
    """用户座位后面那个独立、使用工具调用的 LLM。"""

    def __init__(self, name: str, role: Role, voice: SimulatedVoiceSession, *, model=None):
        super().__init__(name, role, offline=False)
        self.voice = voice
        self.simulator_model = model
        self.is_simulated_user = True
        self.is_user = True

    def _tool_call(self, *, tool_name: str, description: str, properties: dict,
                   required: List[str], instruction: str, players: List[str]):
        """强制模拟用户通过唯一合法的工具调用完成本回合动作。"""
        messages = [
            {"role": "system", "content": (
                self._system_prompt(players)
                + "\n你是独立的用户模拟器。请像有策略的真人玩家一样推理，并且必须调用给定工具完成当前回合。"
                + "\n证据纪律：把公开身份声明与自己确定知道的事实逐项比较。正确说出你的阵营是支持该声明的证据，"
                  "但不是绝对证明；矛盾声明则是反证。不要仅因某人公开了神职身份就投他，尤其不要在没有对跳或矛盾时"
                  "仅凭‘过早跳身份’放逐唯一的预言家声明者。怀疑与投票必须引用具体发言、查验声明或既有投票记录。"
            )},
            {"role": "user", "content": (
                f"【你目前掌握的信息（仅你可见）】\n{self._context_block()}\n\n"
                f"【当前任务】\n{instruction}"
            )},
        ]
        tool = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        }
        client = agent_module.get_client()
        # 模拟器可用独立模型；默认与其他玩家相同（统一 .env 配置）
        model = self.simulator_model or client.model_name
        response = agent_module._safe_create(
            client,
            model=model,
            messages=messages,
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": tool_name}},
            temperature=0.8,
            max_tokens=512,
        )
        message = response.choices[0].message
        calls = message.tool_calls or []
        if len(calls) != 1 or calls[0].function.name != tool_name:
            raise RuntimeError(f"用户模拟器没有调用必需的工具 {tool_name}")
        try:
            arguments = json.loads(calls[0].function.arguments)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("用户模拟器返回了非法的工具参数") from exc
        self.voice.record_llm_decision(
            seat=self.name,
            tool=tool_name,
            arguments=arguments,
            response_id=getattr(response, "id", None),
            requested_model=model,
            provider_reported_model=getattr(response, "model", None),
            usage=_usage_dict(getattr(response, "usage", None)),
        )
        return arguments

    def speak(self, players: List[str]) -> str:
        """白天公开发言：工具调用产出文本 → 合成语音 → ASR 回读。"""
        arguments = self._tool_call(
            tool_name="speak_publicly",
            description="提交模拟用户的狼人杀公开发言。",
            properties={
                "utterance": {
                    "type": "string",
                    "description": "自然、简洁的中文公开发言，2~4 个短句。",
                }
            },
            required=["utterance"],
            instruction=(
                "现在轮到你公开发言。结合私有记忆和公开历史进行真实的社交推理。"
                "狼人应隐藏身份；好人应引用证据。请用简洁的中文发言，"
                "然后调用 speak_publicly。"
            ),
            players=players,
        )
        utterance = str(arguments.get("utterance", "")).strip()
        if not utterance:
            raise RuntimeError("用户模拟器提交了空发言")
        return self.voice.roundtrip_user(self.name, utterance, self._round_no())

    def _round_no(self) -> int:
        """从法官设置的当前回合或私有记忆里推断当前回合数。"""
        if hasattr(self, "current_round"):
            return int(self.current_round)
        rounds = []
        for item in self.memory:
            import re
            rounds.extend(int(value) for value in re.findall(r"第(\d+)回合", item))
        return max(rounds, default=0)

    def _choose(self, *, prompt: str, candidates: List[str], players: List[str],
                allow_none: bool, action: str) -> Optional[str]:
        """夜间选目标 / 投票的统一入口：工具选择 → 中文话术 → 语音回环 → 解析校验。"""
        choices = list(candidates) + (["none"] if allow_none else [])
        arguments = self._tool_call(
            tool_name="choose_player",
            description="恰会选择一个合法的玩家目标；允许时也可明确放弃。",
            properties={
                "target": {"type": "string", "enum": choices},
                "reason": {"type": "string", "description": "一句简短的策略理由。"},
            },
            required=["target", "reason"],
            instruction=(
                f"{prompt}\n合法目标：{'、'.join(choices)}。这是 {action} 行动。"
                "只依据你的私有记忆和公开信息推理，然后调用 choose_player。"
            ),
            players=players,
        )
        target = str(arguments.get("target", "")).strip()
        if target not in choices:
            raise RuntimeError(f"用户模拟器选择了非法目标 {target!r}")
        self.last_decision_reason = str(arguments.get("reason", "")).strip() or None
        expected = None if target == "none" else target
        # 把工具选择转成固定中文话术，走真实的语音回环（TTS → ASR）
        if expected is None:
            spoken = "我选择弃票。"
        else:
            number = int(expected[1:])
            chinese = {
                1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
                6: "六", 7: "七", 8: "八", 9: "九", 10: "十",
            }
            spoken = f"我选择{chinese.get(number, str(number))}号玩家。"
        transcript = self.voice.roundtrip_user(self.name, spoken, self._round_no())
        # 用与真人座位相同的解析器从转写文本还原目标，校验语音边界没有改变动作
        parsed = HumanPlayerAgent._spoken_target(transcript, candidates, allow_none)
        explicit_abstention = expected is not None or HumanPlayerAgent._explicit_none(transcript)
        if parsed != expected or not explicit_abstention:
            self.voice._event(
                "simulator_action_mismatch",
                action=action,
                tool_target=target,
                asr_transcript=transcript,
                parsed_target=parsed,
            )
            raise RuntimeError(
                f"语音边界改变了模拟器的动作：工具={target}，转写={transcript!r}，解析={parsed}"
            )
        return expected

    def choose_target(self, prompt: str, candidates: List[str], players: List[str],
                      allow_none: bool = False) -> Optional[str]:
        """夜间行动（刀人 / 查验 / 用药）的模拟用户实现。"""
        return self._choose(
            prompt=prompt,
            candidates=candidates,
            players=players,
            allow_none=allow_none,
            action="夜间选目标",
        )

    def vote(self, candidates: List[str], players: List[str]) -> Optional[str]:
        """白天投票的模拟用户实现。"""
        return self._choose(
            prompt=(
                "现在是白天投票放逐环节，选出你认为最可能是狼人的玩家。好人阵营必须"
                "按证据强度决策：没有对跳且已报告自洽查验结果的预言家声明是当前最强"
                "公开证据；除非有具体矛盾或另一名预言家对跳，不得投该声明者。若其报告"
                "某玩家是狼人，应优先投被查杀者；被查杀者仅仅否认不构成矛盾或对跳。"
                "理由必须引用具体发言、查验或既有票型。"
            ),
            candidates=candidates,
            players=players,
            allow_none=True,
            action="投票",
        )
