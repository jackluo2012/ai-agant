#!/usr/bin/env python3
"""在不读取任何凭据的前提下报告实验 10-5 的持久化进度。"""

from __future__ import annotations

import argparse
import gzip
import json
import os
from pathlib import Path


ARMS = ("baseline", "custom_goal", "no_reflection")


def process_alive(pid: int | None) -> bool:
    """用 0 号信号探测进程是否存活。"""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def receipt_rows(path: Path) -> int:
    """统计回执文件（支持 gzip）的行数。"""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def main() -> int:
    parser = argparse.ArgumentParser(description="实验进度只读监视器")
    parser.add_argument("output", type=Path, help="实验输出目录")
    args = parser.parse_args()
    output = args.output.resolve()
    launch_path = output / "launch.json"
    launch_by_arm = {}
    if launch_path.exists():
        launch = json.loads(launch_path.read_text(encoding="utf-8"))
        launch_by_arm = {row["arm"]: row for row in launch.get("launches", [])}
    # 监督器的进程号比启动器更新，优先采用
    supervisor_path = output / "supervisor_status.json"
    if supervisor_path.exists():
        supervisor = json.loads(supervisor_path.read_text(encoding="utf-8"))
        for arm, pid in supervisor.get("pids", {}).items():
            launch_by_arm.setdefault(arm, {})["pid"] = pid
    result = {"seed": None, "arms": {}}
    seed_path = output / "seed_status.json"
    if seed_path.exists():
        result["seed"] = json.loads(seed_path.read_text(encoding="utf-8"))
    else:
        # 种子尚未完成时报告实时回执的调用数
        live = output / "receipts" / "seed_history.jsonl"
        result["seed"] = {
            "complete": False,
            "live_receipt_calls": receipt_rows(live) if live.exists() else 0,
        }
    for arm in ARMS:
        status_path = output / "status" / f"{arm}.json"
        status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {
            "completed_steps": 0,
            "target_steps": 17_280,
            "complete": False,
            "checkpoints": [],
        }
        launch = launch_by_arm.get(arm, {})
        status["pid"] = launch.get("pid")
        status["process_alive"] = process_alive(launch.get("pid"))
        receipt_dir = output / "receipts" / arm
        # 只统计未隔离的实时回执
        live = (
            sorted(
                path
                for path in receipt_dir.glob("*.jsonl")
                if ".failed-" not in path.name
            )
            if receipt_dir.exists()
            else []
        )
        status["live_receipt_calls"] = sum(receipt_rows(path) for path in live)
        result["arms"][arm] = status
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
