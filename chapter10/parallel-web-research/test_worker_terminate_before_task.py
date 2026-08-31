"""回归测试：任务派发前收到终止广播时，Worker 必须正确退出而不是挂死。"""

import asyncio
import pytest
import sys
import os
from pathlib import Path

# 添加项目根目录到路径，确保能导入统一的 llm 封装模块
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径，便于独立运行时导入同目录模块
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from agents import WorkerAgent
from message_bus import MessageBus, BROADCAST
from sources import Website


@pytest.mark.asyncio
async def test_worker_exits_early_when_terminate_arrives_before_task_assigned():
    """契约验证：terminate 先于 task_assigned 到达时，Worker 不挂死、不忽略信号。

    锁定的历史缺陷：Worker 在等待 task_assigned 时死循环、忽略终止信号。
    """
    bus = MessageBus(verbose=False)
    site = Website("s1", "College 1", "http://site1.edu")
    w = WorkerAgent("worker-1", site, bus, "target", None)

    # 在 Worker 拿到 task_assigned 之前先广播 terminate
    await bus.send("coordinator", BROADCAST, "terminate", {"reason": "target_found_by_other"})

    # w.run() 必须及时退出（而不是一直等 task_assigned）、置位终止事件并回执确认
    await asyncio.wait_for(w.run(), timeout=2.0)

    assert w.terminate.is_set()
    assert w._termination_reason == "target_found_by_other"
    acks = [m for m in bus.history if m.type == "ack" and m.sender_id == "worker-1"]
    assert len(acks) == 1
    assert acks[0].payload.get("acked") == "terminate"
