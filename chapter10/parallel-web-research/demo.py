#!/usr/bin/env python3
"""实验 10-4：N 个真实浏览器会话并行搜索教师。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import os
import time
from pathlib import Path

# 添加项目根目录到路径，确保能导入统一的 llm 封装模块
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径，便于独立运行时导入同目录模块
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from agents import BrowserPool, Coordinator, WorkerAgent, run_sequential
from message_bus import MessageBus
from sources import DEFAULT_SITES, TARGET, load_sites


def parse_args():
    """解析命令行参数（LLM 配置自动从项目根目录 .env 读取）。"""
    p = argparse.ArgumentParser(description="实验 10-4：N 个独立真实浏览器会话并行搜索教师")
    p.add_argument("--target", default=TARGET, help="要查找的教师姓名")
    p.add_argument("--sites-json", help="网站数组 JSON，每项包含 name/college/url")
    p.add_argument("--agents", type=int, default=len(DEFAULT_SITES), help="使用前 N 个网站/Agent")
    p.add_argument("--timeout", type=float, default=120, help="每网站超时秒数")
    p.add_argument("--headed", action="store_true", help="显示每个真实浏览器页面")
    p.add_argument("--quiet", action="store_true", help="不打印逐条总线消息")
    p.add_argument("--no-compare", action="store_true", help="跳过串行基线（默认真实运行并对比）")
    p.add_argument("--output", default="results/latest.json", help="保存实测结果 JSON")
    return p.parse_args()


async def main(args) -> int:
    """主流程：并行阶段 → 可选串行基线 → 汇总证据并审计资源清理。"""
    sites = load_sites(args.sites_json, args.agents)
    print(f"真实目标：{args.target}; 真实网站/独立浏览器上下文数：{len(sites)}")

    # —— 并行阶段：动态为每个网站启动一个同构 Worker ——
    parallel_pool = BrowserPool(headless=not args.headed)
    await parallel_pool.start()
    try:
        bus = MessageBus(verbose=not args.quiet)
        coordinator = Coordinator(bus, args.target)
        for i, site in enumerate(sites):
            coordinator.add_worker(WorkerAgent(
                f"agent-{i:02d}", site, bus, args.target, parallel_pool, args.timeout
            ))
        parallel = await coordinator.run()
    finally:
        await parallel_pool.close()

    # —— 串行基线：访问同一批真实网站，实测（而非估算）加速比 ——
    serial = None
    serial_pool = None
    if not args.no_compare:
        serial_pool = BrowserPool(headless=not args.headed)
        await serial_pool.start()
        try:
            serial = await run_sequential(sites, args.target, serial_pool, args.timeout)
        finally:
            await serial_pool.close()

    # 汇总实验证据：结果 + 资源审计 + 实测加速比
    evidence = {
        "target": args.target,
        "sites": [site.__dict__ for site in sites],
        "parallel": parallel,
        "serial": serial,
        "resource_audit": {
            "parallel_contexts_created": parallel_pool.contexts_created,
            "parallel_contexts_closed": parallel_pool.contexts_closed,
            "serial_contexts_created": serial_pool.contexts_created if serial_pool else 0,
            "serial_contexts_closed": serial_pool.contexts_closed if serial_pool else 0,
        },
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if serial and parallel["parallel_seconds"]:
        # 实测加速比 = 串行耗时 / 并行耗时
        evidence["measured_speedup"] = round(serial["seconds"] / parallel["parallel_seconds"], 3)
    # 写入结果文件并回显完整证据
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))

    # —— 验收门禁：资源清理 / 单次级联广播 / 败者确认完整 ——
    resources_ok = parallel_pool.contexts_created == parallel_pool.contexts_closed
    single_cascade = parallel["winner"] is None or parallel["terminate_broadcasts"] == 1
    acknowledgements_ok = not parallel["missing_loser_acks"]
    print(f"资源清理：{'通过' if resources_ok else '失败'}; 单次级联广播：{'通过' if single_cascade else '失败'}")
    if parallel["winner"] is None:
        print(f"搜索完成：未找到目标教师；失败统计={parallel['failure_summary']}")
    return 0 if resources_ok and single_cascade and acknowledgements_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(parse_args())))
