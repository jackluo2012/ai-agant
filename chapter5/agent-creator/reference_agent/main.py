"""生成的 Agent 的主入口"""
from __future__ import annotations

import argparse
import json
import sys

# 添加项目根目录到路径
import os
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from agent import GeneratedAgent


def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(description="运行生成的 Agent")
    parser.add_argument("--task", required=True, help="要执行的任务")
    parser.add_argument("--model", help="模型名称（可选）")
    parser.add_argument("--history-json", default="[]", help="历史记录 JSON（可选）")
    args = parser.parse_args()
    history = json.loads(args.history_json)
    if not isinstance(history, list):
        raise SystemExit("--history-json 必须解码为列表")
    result = GeneratedAgent(model=args.model).run(args.task, history=history)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
