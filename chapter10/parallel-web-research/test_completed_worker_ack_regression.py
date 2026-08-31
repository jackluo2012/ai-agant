"""回归测试：胜者结算前已自行完成的 Worker 不得被误报为缺失确认。"""

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

from agents import Coordinator, TaskRecord
from message_bus import MessageBus
from sources import Website

@pytest.mark.asyncio
async def test_worker_completing_before_winner_is_not_reported_as_missing_ack():
    """契约验证：结算前已因 not_found 或错误完成的 Worker，不进入 expected_loser_acks。

    锁定的历史缺陷：胜者结算时把已自行完成的 Worker 误报为"缺失败者确认"。
    """
    bus = MessageBus(verbose=False)
    coordinator = Coordinator(bus, "target")

    site1 = Website("Site 1", "College 1", "https://site1.edu")
    site2 = Website("Site 2", "College 2", "https://site2.edu")
    site3 = Website("Site 3", "College 3", "https://site3.edu")

    # 为协调器构造假的 Worker 对象（不启动真实浏览器）
    class FakeWorker:
        def __init__(self, wid, site):
            self.id = wid
            self.site = site
            self.timeout = 10
        async def run(self):
            pass

    workers = [
        FakeWorker("worker-1", site1),
        FakeWorker("worker-2", site2),
        FakeWorker("worker-3", site3),
    ]

    for w in workers:
        coordinator.add_worker(w)

    # Worker 1 在结算之前就已完成（not_found）
    await bus.send("worker-1", "coordinator", "not_found", {"reason": "not found", "source": "Site 1"})
    await bus.send("worker-1", "coordinator", "resource_closed", {"browser_context_closed": True, "source": "Site 1"})

    # Worker 2 找到目标（胜者）
    await bus.send("worker-2", "coordinator", "target_found", {"data": {"found": True}, "source": "Site 2"})
    await bus.send("worker-2", "coordinator", "resource_closed", {"browser_context_closed": True, "source": "Site 2"})

    # Worker 3 收到终止广播并确认
    await bus.send("worker-3", "coordinator", "ack", {"acked": "terminate", "source": "Site 3"})
    await bus.send("worker-3", "coordinator", "resource_closed", {"browser_context_closed": True, "source": "Site 3"})

    result = await coordinator.run()

    # 断言：期望确认集合只包含 Worker 3，缺失确认列表为空
    assert result["winner"] == "worker-2"
    assert result["expected_loser_acks"] == ["worker-3"]
    assert result["missing_loser_acks"] == []


@pytest.mark.asyncio
async def test_worker_completing_after_winner_still_owes_ack():
    """结算时刻仍在运行的 Worker 仍欠确认：期望集合在结算时快照。"""
    bus = MessageBus(verbose=False)
    coordinator = Coordinator(bus, "target")

    class FakeWorker:
        timeout = 10

        def __init__(self, wid):
            self.id = wid
            self.site = Website(wid, wid, f"https://{wid}.edu")

        async def run(self):
            pass

    for worker_id in ("worker-1", "worker-2"):
        coordinator.add_worker(FakeWorker(worker_id))

    await bus.send("worker-2", "coordinator", "target_found", {"data": {"found": True}})
    await bus.send("worker-1", "coordinator", "not_found", {"reason": "finished after settlement"})
    for worker_id in ("worker-1", "worker-2"):
        await bus.send(worker_id, "coordinator", "resource_closed", {"browser_context_closed": True})

    result = await coordinator.run()

    # 断言：结算后才完成的 Worker 1 仍被记为缺失确认
    assert result["expected_loser_acks"] == ["worker-1"]
    assert result["missing_loser_acks"] == ["worker-1"]
