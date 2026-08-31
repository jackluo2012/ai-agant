"""Phone 与 Computer 两个 Agent，以及自主工具分发器。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

from browser import RecoverableFillError, RegistrationBrowser
from bus import MessageBus
from models import DecisionRecord, FieldSpec
from voice import PhoneChannel

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


# 字段值抽取的 provider 凭据留痕（不含任何值本身）
_EXTRACTION_RECEIPTS: List[Dict[str, object]] = []


def reset_extraction_receipts() -> None:
    _EXTRACTION_RECEIPTS.clear()


def extraction_receipts() -> List[Dict[str, object]]:
    """返回不含任何值的 provider 元数据，用于实验溯源。"""
    return [dict(item) for item in _EXTRACTION_RECEIPTS]


def _build_client():
    """获取统一 LLM 客户端（自动读取项目根目录 .env 配置）。"""
    if get_llm_client is None:
        raise RuntimeError(
            "无法导入统一 LLM 客户端 llm.client。"
            "请在项目根目录 ai-agant 下运行（需包含 llm/ 目录）。"
        )
    return get_llm_client()


async def _extract_value(field: FieldSpec, utterance: str) -> str:
    """用 Phone Agent 的 LLM 把一句口语化回答抽取为单个字段值。"""
    client = _build_client()
    model = client.model_name
    provider = client.provider

    kwargs = dict(messages=[
            {
                "role": "system",
                "content": (
                    "只抽取用户针对指定表单字段提供的那个值。绝不要推断或补全缺失的值。"
                    "标识符必须逐字保留；当字段要求时，把明确说出的 email 用词（如'艾特'、'at'）"
                    "还原为符号，把口语数字词还原为数字。只返回一个 JSON 对象，"
                    "格式为 {\"value\": \"抽取出的值\"}。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "field": field.label,
                        "type": field.input_type,
                        "format_hint": field.format_hint,
                        "options": field.options,
                        "spoken_answer": utterance,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        response_format={"type": "json_object"},
    )
    # kimi 系列模型需要显式的 temperature/max_tokens 才能稳定输出 JSON
    model_kwargs = dict(kwargs)
    if "kimi" in model:
        model_kwargs["temperature"] = 1
        model_kwargs["max_tokens"] = 2048
    # 统一客户端是同步实现，放到线程池中执行，避免阻塞 Computer Agent 的填写循环
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create, model=model, **model_kwargs
        )
    except Exception as exc:
        raise RuntimeError(
            f"Phone Agent 字段抽取调用失败（provider={provider}，model={model}）：{type(exc).__name__}"
        ) from exc
    if not (response.choices[0].message.content or "").strip():
        raise ValueError("模型返回空 content")
    data = json.loads(response.choices[0].message.content or "{}")
    # 记录无值的 provider 凭据元数据
    usage = getattr(response, "usage", None)
    _EXTRACTION_RECEIPTS.append({
        "operation": "field_value_extraction",
        "provider": provider,
        "model": model,
        "response_id": getattr(response, "id", None),
        "usage": {
            key: int(value)
            for key, value in {
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }.items()
            if value is not None
        },
        "transcript_or_value_retained": False,
    })
    return str(data.get("value", "")).strip()


class PhoneAgent:
    """电话侧 Agent：逐项提问、校验格式，并把每个值实时发给电脑侧。"""

    def __init__(
        self,
        bus: MessageBus,
        channel: PhoneChannel,
        purpose: str,
        required_info: List[FieldSpec],
        *,
        max_retries: int = 3,
    ):
        self.bus = bus
        self.channel = channel
        self.purpose = purpose
        self.required_info = required_info
        self.max_retries = max_retries
        self.browser_feedback: List[Dict[str, str]] = []
        self.form_ready = asyncio.Event()

    async def _receive_computer_feedback(self):
        """独立的入站循环：Computer -> Phone 不是只写通道。"""
        while True:
            message = await self.bus.receive("phone_agent")
            if message.type == "fill_error":
                self.browser_feedback.append({
                    "field": str(message.payload.get("field", "")),
                    "error": str(message.payload.get("error", "")),
                })
            elif message.type == "form_ready":
                self.form_ready.set()
                return

    async def run(self) -> None:
        """运行对话，并在任何退出路径上都释放入站循环与传输层。"""
        self._feedback_task = None
        try:
            await self._run_dialogue()
        finally:
            if self._feedback_task is not None:
                self._feedback_task.cancel()
                await asyncio.gather(self._feedback_task, return_exceptions=True)
            if hasattr(self.channel, "close") and not getattr(self.channel, "closed", False):
                await self.channel.close()

    async def _run_dialogue(self) -> None:
        # 入站反馈循环与提问循环并行运行
        feedback_task = asyncio.create_task(
            self._receive_computer_feedback(), name="phone-inbound-computer-messages"
        )
        self._feedback_task = feedback_task
        await self.bus.send(
            "phone_agent", "computer_agent", "call_started",
            purpose=self.purpose,
            fields=[f.name for f in self.required_info],
        )
        await self.channel.say(f"您好，我正在{self.purpose}。我会逐项询问并核对格式。")

        for field in self.required_info:
            accepted = False
            feedback = ""
            for attempt in range(1, self.max_retries + 1):
                question = f"请问您的{field.label}是什么？"
                if field.format_hint:
                    question += f" 格式要求：{field.format_hint}。"
                # 上一次校验失败的原因要复述给用户，帮助其更正
                if feedback:
                    question = f"刚才的回答无法通过校验：{feedback}。{question}"
                await self.bus.send(
                    "phone_agent", "computer_agent", "question_asked",
                    field=field.name,
                    attempt=attempt,
                )
                await self.channel.say(question)
                try:
                    utterance = await self.channel.listen()
                    # 可选字段的空回答是用户主动跳过，而不是要写进有状态页面
                    # 控件的值（某些日期控件对程序化写入空串会产生破坏性反应）。
                    value = "" if not field.required and not utterance.strip() else await _extract_value(field, utterance)
                except Exception as exc:
                    await self.bus.send(
                        "phone_agent", "computer_agent", "call_failed",
                        field=field.name, reason=f"语音/抽取失败：{type(exc).__name__}",
                    )
                    if hasattr(self.channel, "close"):
                        await self.channel.close()
                    feedback_task.cancel()
                    await asyncio.gather(feedback_task, return_exceptions=True)
                    return
                valid, feedback = field.validate(value)
                if not valid:
                    await self.bus.send(
                        "phone_agent", "computer_agent", "format_invalid",
                        field=field.name,
                        attempt=attempt,
                        reason=feedback,
                    )
                    continue

                if not value and not field.required:
                    await self.bus.send(
                        "phone_agent", "computer_agent", "info_skipped",
                        field=field.name, attempt=attempt, reason="optional_blank",
                    )
                    accepted = True
                    break

                await self.bus.send(
                    "phone_agent",
                    "computer_agent",
                    "info_collected",
                    sensitive_keys=("value",),
                    field=field.name,
                    value=value,
                    attempt=attempt,
                )
                # 刻意不等待浏览器的确认回执：Computer Agent 定位/填写该字段
                # 的同时，下一个问题已经开始，问与填逐字段并行。
                accepted = True
                break
            if not accepted:
                await self.bus.send(
                    "phone_agent", "computer_agent", "call_failed",
                    field=field.name,
                    reason="超过格式重问次数",
                )
                await self.channel.say("抱歉，这一项多次未通过格式校验，本次注册已安全暂停。")
                if hasattr(self.channel, "close"):
                    await self.channel.close()
                feedback_task.cancel()
                await asyncio.gather(feedback_task, return_exceptions=True)
                return

        await self.bus.send("phone_agent", "computer_agent", "task_completed")
        # 问/填在逐字段意义上全程并行；只有最后的结束语等待 Computer Agent
        # 的汇总结果，以便浏览器的错误能够回流到通话侧。
        try:
            await asyncio.wait_for(self.form_ready.wait(), timeout=60)
        except asyncio.TimeoutError:
            self.browser_feedback.append({"field": "form", "error": "电脑端最终确认超时"})
        if self.browser_feedback:
            await self.channel.say("信息已收集，但电脑端填写遇到问题，表单已暂停提交，请稍后查看错误报告。")
        else:
            await self.channel.say("所需信息已经收集并填写完成，电脑端已完成最后确认。")
        if hasattr(self.channel, "close"):
            await self.channel.close()
        feedback_task.cancel()
        await asyncio.gather(feedback_task, return_exceptions=True)


class ComputerAgent:
    """电脑侧 Agent：把收集到的值并发写进真实页面，出错时阻止提交。"""

    def __init__(
        self,
        bus: MessageBus,
        browser: RegistrationBrowser,
        field_specs: List[FieldSpec],
        known_values: Dict[str, str],
    ):
        self.bus = bus
        self.browser = browser
        self.fields = {f.name: f for f in field_specs}
        self.known_values = known_values
        self.filled: List[str] = []
        self.errors: List[Dict[str, str]] = []
        self.submitted = False

    async def _fill(self, name: str, value: str) -> None:
        field = self.fields.get(name)
        if not field:
            raise KeyError(f"页面中不存在字段 {name}")
        await self.browser.fill(field, value)
        self.filled.append(name)
        await self.bus.send("computer_agent", "phone_agent", "field_filled", field=name)

    async def _report_fill_error(self, name: str, exc: RecoverableFillError) -> None:
        """记录一次浏览器填写失败，并转发共享的错误信封。"""
        error = {"field": name, "error": str(exc)}
        self.errors.append(error)
        await self.bus.send(
            "computer_agent",
            "phone_agent",
            "fill_error",
            sensitive_keys=("error",),
            **error,
        )

    async def run(self) -> Dict[str, object]:
        # 先填写上下文里已知的字段
        for name, value in self.known_values.items():
            if name in self.fields:
                try:
                    await self._fill(name, value)
                except RecoverableFillError as exc:
                    # 与下面对话中的填写路径保持一致：把失败上报给 Phone Agent
                    # （经 browser_feedback），避免在已知字段失败时仍告诉用户注册成功。
                    await self._report_fill_error(name, exc)

        completed = False
        while not completed:
            # 这里的空闲上限必须大于电话侧单个问题的最坏延迟
            # （TTS + 通道自身的收听窗口 + 值抽取）。WebRTC 真人收听默认允许
            # 一个开始计时器加一个回答计时器（合计约 240 秒），因此这里若只有
            # 120 秒会在用户仍在正常作答时误杀真实通话。run_parallel 会在电话
            # 任务完成或出错的瞬间取消本任务，所以更大的上限只会放宽误杀场景。
            message = await self.bus.receive("computer_agent", timeout=600)
            if message.type == "info_collected":
                name = message.payload.get("field")
                value = message.payload.get("value")
                # 消息格式防御：缺失字段名或值类型不对时立即失败
                if not isinstance(name, str) or not name:
                    raise ValueError("info_collected 必须携带非空的 field")
                if not isinstance(value, str):
                    raise ValueError("info_collected 必须携带字符串 value")
                try:
                    await self._fill(name, value)
                except RecoverableFillError as exc:
                    await self._report_fill_error(name, exc)
            elif message.type == "call_failed":
                self.errors.append({
                    "field": message.payload.get("field", ""),
                    "error": message.payload.get("reason", "Phone Agent 失败"),
                })
                completed = True
            elif message.type == "task_completed":
                completed = True
            elif message.type == "info_skipped":
                # 可选字段的空值不需要任何浏览器操作。显式信封让两个 Agent
                # 的时间线保持可审计。
                continue

        # 有任何错误残留时禁止提交表单
        if not self.errors:
            self.submitted = await self.browser.submit()
        await self.bus.send(
            "computer_agent", "phone_agent", "form_ready",
            errors=len(self.errors), submitted=self.submitted,
        )
        await self.bus.send(
            "computer_agent", "manager", "registration_finished",
            filled=self.filled,
            submitted=self.submitted,
            errors=self.errors,
        )
        return {
            "filled": self.filled,
            "submitted": self.submitted,
            "errors": self.errors,
        }


@dataclass
class SpawnedAgents:
    """一次工具调用派生出的一对 Agent。"""

    phone: PhoneAgent
    computer: ComputerAgent


def initiate_phone_call_agent(
    *,
    decision: DecisionRecord,
    bus: MessageBus,
    channel: PhoneChannel,
    browser: RegistrationBrowser,
    known_values: Dict[str, str],
) -> SpawnedAgents:
    """工具分发器：只有在模型真的发出工具调用之后才会被触发。"""
    if decision.tool_called != "initiate_phone_call_agent":
        raise RuntimeError("模型未调用 initiate_phone_call_agent，不能预先创建 Phone Agent")
    if not decision.required_info:
        raise RuntimeError("Phone Agent 工具调用没有任何可映射的页面字段")
    return SpawnedAgents(
        phone=PhoneAgent(bus, channel, decision.purpose, decision.required_info),
        computer=ComputerAgent(bus, browser, decision.discovered_fields, known_values),
    )


async def run_parallel(agents: SpawnedAgents, bus: MessageBus) -> Dict[str, object]:
    """并行运行两个 Agent；任一方异常时取消对方并关闭传输层。"""
    phone_task = asyncio.create_task(agents.phone.run(), name="phone-agent-react-loop")
    computer_task = asyncio.create_task(agents.computer.run(), name="computer-agent-react-loop")
    tasks = (phone_task, computer_task)
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        failure = next(
            (task.exception() for task in done if not task.cancelled() and task.exception() is not None),
            None,
        )
        if failure is not None:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise failure
        _phone_result, computer_result = await asyncio.gather(*tasks)
    except BaseException:
        # 当一个任务抛出异常时，``asyncio.gather`` 不会自动取消仍在运行的对方。
        # 音频/浏览器循环的失败不能把另一个 Agent 留在收件箱上永久阻塞，
        # 也不能让 PSTN/webhook 传输层保持打开。
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        channel = agents.phone.channel
        if hasattr(channel, "close") and not getattr(channel, "closed", False):
            await channel.close()
        raise
    finished = await bus.receive("manager", timeout=5)
    assert finished.type == "registration_finished"
    return computer_result


def timing_evidence(bus: MessageBus) -> Dict[str, object]:
    """从消息历史提取问/填时间线，证明相邻字段存在问填重叠。"""
    questions = {
        m.payload["field"]: m.monotonic_seconds
        for m in bus.history if m.type == "question_asked" and m.payload.get("attempt") == 1
    }
    collected = {
        m.payload["field"]: m.monotonic_seconds
        for m in bus.history if m.type == "info_collected"
    }
    filled = {
        m.payload["field"]: m.monotonic_seconds
        for m in bus.history if m.type == "field_filled"
    }
    ordered = list(questions)
    overlaps = []
    expected_overlap_count = 0
    # 逐个检查相邻字段对：下一问是否发生在上一字段填写完成之前
    for current, next_field in zip(ordered, ordered[1:]):
        if current in collected and current in filled:
            expected_overlap_count += 1
            overlaps.append({
                "field_being_filled": current,
                "next_question": next_field,
                "next_question_before_fill_completed": questions[next_field] < filled[current],
                "next_question_at": questions[next_field],
                "fill_completed_at": filled[current],
            })
    return {
        "question_times": questions,
        "collection_times": collected,
        "fill_times": filled,
        "overlap_checks": overlaps,
        "expected_overlap_count": expected_overlap_count,
        "independent_tasks": ["phone-agent-react-loop", "computer-agent-react-loop"],
    }
