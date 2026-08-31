"""两个实时 Agent 之间的异步、带时间戳的点对点消息总线。"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, List, Optional

from models import AgentMessage


class MessageBus:
    """消息总线：每个接收者一个队列，全部消息按序写入时序轨迹文件。"""

    def __init__(self, trace_path: Optional[str] = None):
        self.started = time.monotonic()
        self._sequence = 0
        self._queues: DefaultDict[str, asyncio.Queue[AgentMessage]] = defaultdict(asyncio.Queue)
        self.history: List[AgentMessage] = []
        self.trace_path = Path(trace_path) if trace_path else None

    async def send(
        self,
        sender: str,
        recipient: str,
        type: str,
        *,
        sensitive_keys: tuple[str, ...] = (),
        **payload,
    ) -> AgentMessage:
        """
        发送一条点对点消息，并同步落盘到轨迹文件

        Args:
            sender: 发送方标识
            recipient: 接收方标识
            type: 消息类型
            sensitive_keys: 需要在控制台/磁盘中脱敏的负载键
            **payload: 消息负载

        Returns:
            已构造的 AgentMessage
        """
        self._sequence += 1
        message = AgentMessage(
            sender=sender,
            recipient=recipient,
            type=type,
            payload=payload,
            sequence=self._sequence,
            monotonic_seconds=round(time.monotonic() - self.started, 6),
            wall_time=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        )
        self.history.append(message)
        # 投递到接收者队列（接收者拿到完整值）
        await self._queues[recipient].put(message)
        # 控制台打印时对敏感键脱敏
        printable = {k: ("<redacted>" if k in sensitive_keys else v) for k, v in payload.items()}
        # 脱敏策略与内存信封绑定在一起：接收者拿到真实值，
        # 而控制台/磁盘轨迹永不保留语音录入的个人数据。
        setattr(message, "_sensitive_keys", sensitive_keys)
        print(
            f"[t={message.monotonic_seconds:8.3f}s #{message.sequence:03d}] "
            f"{sender} -> {recipient} | {type} | "
            f"{json.dumps(printable, ensure_ascii=False)}"
        )
        self.flush()
        return message

    async def receive(self, recipient: str, timeout: Optional[float] = None) -> AgentMessage:
        """接收一条消息；timeout 为 None 时无限等待。"""
        get = self._queues[recipient].get()
        return await asyncio.wait_for(get, timeout) if timeout else await get

    def flush(self) -> None:
        """把当前全部历史消息（含脱敏）写回轨迹文件。"""
        if not self.trace_path:
            return
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for message in self.history:
            row = message.to_dict()
            keys = getattr(message, "_sensitive_keys", ())
            # 磁盘轨迹对敏感键统一脱敏
            row["payload"] = {
                k: ("<redacted>" if k in keys else v) for k, v in row["payload"].items()
            }
            rows.append(row)
        self.trace_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
