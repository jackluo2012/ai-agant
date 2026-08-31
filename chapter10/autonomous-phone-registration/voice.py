"""真实麦克风级联语音通道（TTS -> 扬声器 -> 麦克风 -> ASR）与确定性测试通道。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Dict, List, Protocol

# 添加项目根目录到路径，以便导入统一 LLM 客户端
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from llm.client import get_llm_client
except ImportError:
    get_llm_client = None


class PhoneChannel(Protocol):
    """电话语音通道协议：只会说（TTS）与听（ASR）两个方法。"""

    async def say(self, text: str) -> None: ...
    async def listen(self, *, timeout: float = 30.0) -> str: ...


class LiveMicrophoneChannel:
    """真实的级联电话语音回路：TTS 合成 -> 扬声器 -> 麦克风 -> ASR 转录。

    本机麦克风/扬声器就是通话传输层。provider 边界被封装在本类之内，
    因此 PSTN/WebRTC 传输层只需实现同样的两个方法。
    注意：语音合成与识别调用音频 API，要求所配置的端点支持 audio 接口。
    """

    def __init__(self, *, language: str = "zh", voice: str = "coral"):
        if get_llm_client is None:
            raise RuntimeError(
                "无法导入统一 LLM 客户端 llm.client。"
                "请在项目根目录 ai-agant 下运行（需包含 llm/ 目录）。"
            )
        # 使用统一客户端（自动读取项目根目录 .env），并附加音频调用专用超时
        self.client = get_llm_client().with_options(timeout=60, max_retries=1)
        self.language = language
        self.voice = voice
        self.sample_rate = int(os.getenv("VOICE_SAMPLE_RATE", "16000"))
        self.silence_seconds = float(os.getenv("VOICE_SILENCE_SECONDS", "0.9"))
        self.threshold = float(os.getenv("VOICE_RMS_THRESHOLD", "0.012"))
        self.latencies: List[Dict[str, float]] = []

    async def say(self, text: str) -> None:
        """合成语音并经本机播放器播出，记录 TTS 与播放耗时。"""
        started = time.monotonic()
        path = Path(tempfile.mkstemp(suffix=".mp3")[1])

        def synthesize():
            result = self.client.audio.speech.create(
                model=os.getenv("OPENAI_TTS_MODEL", "tts-1"),
                voice=self.voice,
                input=text,
            )
            result.stream_to_file(path)

        try:
            await asyncio.to_thread(synthesize)
            synth_done = time.monotonic()
            # 播放器可通过环境变量替换（macOS 为 afplay，Linux 可用 aplay/ffplay）
            player = os.getenv("AUDIO_PLAYER", "afplay")
            proc = await asyncio.create_subprocess_exec(
                player, str(path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            await proc.wait()
            self.latencies.append({
                "tts_seconds": round(synth_done - started, 3),
                "playback_seconds": round(time.monotonic() - synth_done, 3),
            })
        finally:
            path.unlink(missing_ok=True)

    async def listen(self, *, timeout: float = 30.0) -> str:
        """采集麦克风音频（带 VAD 静音检测），再交由 ASR 转录为文本。"""
        path = Path(tempfile.mkstemp(suffix=".wav")[1])
        started = time.monotonic()
        try:
            await asyncio.to_thread(self._record_vad, path, timeout)
            record_done = time.monotonic()

            def transcribe() -> str:
                with path.open("rb") as audio:
                    response = self.client.audio.transcriptions.create(
                        model=os.getenv("OPENAI_ASR_MODEL", "whisper-1"),
                        file=audio,
                        language=self.language,
                    )
                return response.text.strip()

            text = await asyncio.to_thread(transcribe)
            self.latencies.append({
                "capture_seconds": round(record_done - started, 3),
                "asr_seconds": round(time.monotonic() - record_done, 3),
            })
            print(f"  [ASR] 用户：{text}")
            return text
        finally:
            path.unlink(missing_ok=True)

    def _record_vad(self, path: Path, timeout: float) -> None:
        """录制麦克风输入：检测到语音后，出现句末静音即自动停止。"""
        import numpy as np
        import sounddevice as sd

        block = 1024
        frames = []
        heard_speech = False
        silent_blocks = 0
        # 句末静音所需连续静音块数
        required_silence = max(1, int(self.silence_seconds * self.sample_rate / block))
        deadline = time.monotonic() + timeout
        print("  [麦克风] 请开始回答；检测到句末静音后自动提交……")
        with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype="float32", blocksize=block) as stream:
            while time.monotonic() < deadline:
                data, overflowed = stream.read(block)
                if overflowed:
                    print("  [麦克风] 输入发生 overflow，继续采集")
                mono = data[:, 0].copy()
                frames.append(mono)
                # RMS 能量作为语音活动检测阈值
                rms = float(np.sqrt(np.mean(np.square(mono))))
                if rms >= self.threshold:
                    heard_speech = True
                    silent_blocks = 0
                elif heard_speech:
                    silent_blocks += 1
                    if silent_blocks >= required_silence:
                        break
        if not heard_speech:
            raise TimeoutError("未在规定时间内检测到语音")
        # float32 -> int16 PCM，写入临时 WAV 文件
        pcm = (np.concatenate(frames).clip(-1, 1) * 32767).astype("<i2")
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm.tobytes())


class ScriptedPhoneChannel:
    """脚本化语音通道：仅用于测试与编排调试，不涉及任何音频。"""

    def __init__(self, answers: List[str]):
        self.answers = asyncio.Queue()
        for answer in answers:
            self.answers.put_nowait(answer)
        self.prompts: List[str] = []

    async def say(self, text: str) -> None:
        self.prompts.append(text)
        print(f"  [scripted-phone] {text}")
        await asyncio.sleep(0)

    async def listen(self, *, timeout: float = 30.0) -> str:
        return await asyncio.wait_for(self.answers.get(), timeout)
