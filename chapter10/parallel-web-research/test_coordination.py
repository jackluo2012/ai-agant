"""协调器单元测试：并发结算、数据集校验、错误隔离与超时取消。"""

import asyncio
import sys
import os
from types import SimpleNamespace

import pytest

# 添加项目根目录到路径，确保能导入统一的 llm 封装模块
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径，便于独立运行时导入同目录模块
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from agents import Coordinator
from agents import WorkerAgent
from message_bus import MessageBus
from sources import DEFAULT_SITES, load_sites


@pytest.mark.asyncio
async def test_near_simultaneous_hits_settle_and_broadcast_once():
    """两个 Worker 几乎同时命中时：只结算一个胜者，且只广播一次终止。"""
    bus = MessageBus(verbose=False)
    coordinator = Coordinator(bus, "target")
    # 并发结算两个 Worker，模拟"几乎同时命中"的竞态
    await asyncio.gather(
        coordinator._settle("agent-a", {"name": "target"}),
        coordinator._settle("agent-b", {"name": "target"}),
    )
    # 断言：胜者唯一、后来者被记为重复命中、终止广播只发生一次
    assert coordinator.winner in {"agent-a", "agent-b"}
    assert len(coordinator.duplicate_hits) == 1
    assert sum(m.type == "terminate" for m in bus.history) == 1


def test_default_dataset_is_ten_real_http_university_pages():
    """默认数据集必须是 10 个真实 HTTP 大学页面，且不携带任何模拟内容字段。"""
    sites = load_sites(None)
    assert len(sites) == 10
    assert all(s.url.startswith("https://") for s in sites)
    # 不允许出现 content/latency 之类模拟数据的痕迹
    assert all(not hasattr(s, "content") and not hasattr(s, "latency") for s in sites)


class StubWorker:
    """桩 Worker：按预设脚本依次向协调器发送指定消息，不启动真实浏览器。"""

    def __init__(self, worker_id, bus, events):
        self.id = worker_id
        self.site = SimpleNamespace(
            name=f"source-{worker_id}", url=f"https://example.test/{worker_id}"
        )
        self.bus = bus
        self.events = events
        self.timeout = 0.1
        self.sub = bus.subscribe(worker_id, types=["task_assigned", "terminate"])

    async def run(self):
        # 先等待任务派发，再按脚本顺序发送事件
        assigned = await self.sub.get()
        assert assigned.type == "task_assigned"
        for event_type, payload in self.events:
            if event_type == "status_update":
                payload = {"source": self.site.name, **payload}
            else:
                payload = {**payload, "source": self.site.name}
            await self.bus.send(self.id, "coordinator", event_type, payload)


@pytest.mark.asyncio
async def test_all_not_found_has_no_cascade_and_returns_reason_and_status_aggregation():
    """全部未命中时：不触发级联终止，且返回逐站原因与状态聚合。"""
    bus = MessageBus(verbose=False)
    coordinator = Coordinator(bus, "missing")
    for worker_id in ("agent-a", "agent-b"):
        coordinator.add_worker(StubWorker(worker_id, bus, [
            ("status_update", {"state": "执行中", "note": "reading"}),
            ("not_found", {"reason": "target absent"}),
            ("status_update", {"state": "已完成", "note": "未找到目标"}),
            ("resource_closed", {"browser_context_closed": True}),
        ]))

    result = await coordinator.run()

    # 断言：无胜者、无终止广播、逐站原因与状态表正确
    assert result["outcome"] == "not_found"
    assert result["winner"] is None
    assert result["terminate_broadcasts"] == 0
    assert result["not_found_reasons"] == {
        "agent-a": "target absent", "agent-b": "target absent",
    }
    assert all(row["state"] == "已完成" for row in result["status_table"].values())
    assert result["failure_summary"] == {"count": 0, "by_type": {}}


@pytest.mark.asyncio
async def test_worker_failure_is_isolated_and_summarized_while_peer_completes():
    """单 Worker 失败不影响同伴：失败被隔离记录并按类型汇总。"""
    bus = MessageBus(verbose=False)
    coordinator = Coordinator(bus, "missing")
    # bad：模拟超时失败的 Worker
    coordinator.add_worker(StubWorker("bad", bus, [
        ("worker_error", {"error": "TimeoutError: deadline"}),
        ("status_update", {"state": "失败", "note": "timeout"}),
        ("resource_closed", {"browser_context_closed": True}),
    ]))
    # good：正常完成的 Worker
    coordinator.add_worker(StubWorker("good", bus, [
        ("not_found", {"reason": "target absent"}),
        ("status_update", {"state": "已完成", "note": "peer completed"}),
        ("resource_closed", {"browser_context_closed": True}),
    ]))

    result = await coordinator.run()

    # 断言：失败与未命中各自归位，状态表正确，失败按类型汇总
    assert result["outcome"] == "not_found"
    assert result["errors"] == {"bad": "TimeoutError: deadline"}
    assert result["not_found_reasons"] == {"good": "target absent"}
    assert result["failure_summary"] == {"count": 1, "by_type": {"TimeoutError": 1}}
    assert result["status_table"]["good"]["state"] == "已完成"


@pytest.mark.asyncio
async def test_timeout_cancellation_closes_real_worker_context():
    """Worker 因超时被外层取消时，其真实浏览器上下文必须被关闭。"""

    # 构造一个 inner_text 永远挂起的假页面，模拟"读正文卡死"
    class BlockingPage:
        async def goto(self, *args, **kwargs):
            return None

        def locator(self, _selector):
            return self

        async def inner_text(self, **kwargs):
            await asyncio.Future()

    class Context:
        def __init__(self):
            self.closed = False

        async def new_page(self):
            return BlockingPage()

        async def close(self):
            self.closed = True

    class Pool:
        def __init__(self):
            self.context = Context()
            self.closed = 0

        async def new_context(self):
            return self.context

        async def mark_closed(self):
            self.closed += 1

    bus = MessageBus(verbose=False)
    pool = Pool()
    site = SimpleNamespace(name="blocking", url="https://example.test")
    worker = WorkerAgent("agent-timeout", site, bus, "target", pool, timeout=0.01)
    coordinator_sub = bus.subscribe("coordinator", types=None)
    await bus.send("coordinator", worker.id, "task_assigned", {})

    # 外层管理者的兜底期限会在正文读取挂起期间取消该 Worker
    await asyncio.wait_for(worker.run(), timeout=0.05)

    # 断言：上下文确实关闭、关闭计数入账、协调器收到错误与资源关闭消息
    assert pool.context.closed is True
    assert pool.closed == 1
    messages = []
    while not coordinator_sub.inbox.empty():
        messages.append(coordinator_sub.inbox.get_nowait())
    assert any(m.type == "worker_error" and "TimeoutError" in m.payload["error"] for m in messages)
    assert any(m.type == "resource_closed" and m.payload["browser_context_closed"] for m in messages)
