#!/usr/bin/env python3
"""以分离进程的方式启动或恢复全部实验 10-5 实验臂。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path


ARMS = ("baseline", "custom_goal", "no_reflection")


def main() -> int:
    parser = argparse.ArgumentParser(description="实验臂分离进程启动器")
    parser.add_argument("--upstream", type=Path, required=True, help="上游官方仓库路径")
    parser.add_argument("--output", type=Path, required=True, help="实验输出目录")
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="用于子进程的 Python 解释器")
    parser.add_argument("--target-steps", type=int, default=17_280, help="目标步数")
    parser.add_argument("--chunk-steps", type=int, default=360, help="每个 checkpoint 的步数")
    args = parser.parse_args()
    output = args.output.resolve()
    # 实验臂依赖共享历史种子，必须先完成种子准备
    if not (output / "seed_status.json").exists():
        raise SystemExit("启动实验臂之前请先准备共享历史种子")
    logs = output / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    launches = []
    for arm in ARMS:
        status_path = output / "status" / f"{arm}.json"
        # 已完成的实验臂直接跳过（恢复场景）
        if status_path.exists() and json.loads(status_path.read_text(encoding="utf-8")).get("complete"):
            launches.append({"arm": arm, "skipped": "已完成"})
            continue
        command = [
            str(args.python.expanduser().absolute()),
            str(Path(__file__).resolve().with_name("run_campaign.py")),
            "--upstream",
            str(args.upstream.resolve()),
            "--output",
            str(output),
            "--mode",
            "arm",
            "--arm",
            arm,
            "--target-steps",
            str(args.target_steps),
            "--chunk-steps",
            str(args.chunk_steps),
        ]
        log_path = logs / f"{arm}.log"
        handle = log_path.open("ab", buffering=0)
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            # 工作目录固定在仓库根目录（本文件位于 chapter10/<项目>/ 下）
            cwd=Path(__file__).resolve().parents[2],
            env=os.environ.copy(),
            start_new_session=True,
        )
        handle.close()
        launches.append(
            {
                "arm": arm,
                "pid": process.pid,
                "log": str(log_path.relative_to(output)),
                "command": command,
            }
        )
    record = {
        "schema_version": 1,
        "experiment": "10-5",
        "launched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "launches": launches,
    }
    launch_path = output / "launch.json"
    launch_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
