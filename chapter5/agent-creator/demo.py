"""演示脚本：运行 Agent 创建器实验"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from creator import DEFAULT_PROTOCOL, load_protocol, run_experiment


DEFAULT_REQUIREMENTS = load_protocol()[0]["requirements"]


def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(
        description="实验 5-13：比较从头创建的 Agent 与基于已验证 Agent 修改的 Agent"
    )
    parser.add_argument("--requirements", default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--output", type=Path, default=Path("runs/latest"))
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument(
        "--live-task",
        default=None,
        help="开发专用的单个任务覆盖；它无法完成冻结的书籍实验",
    )
    parser.add_argument("--no-live", action="store_true", help="跳过生成 Agent 的真实 API 执行")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="重用 --output 中已生成的分支并修复/重新验证它们",
    )
    args = parser.parse_args()
    result = run_experiment(
        args.requirements,
        args.output,
        live=not args.no_live,
        live_task=args.live_task,
        resume=args.resume,
        protocol_path=args.protocol,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["official_complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
