"""运行完整的离线自我修改发布流程。"""

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

from evolution import diagnose, generate_candidate, release_manifest, validate_candidate, write_candidate


ROOT = Path(__file__).parent


def main() -> None:
    """主入口点"""
    parser = argparse.ArgumentParser(description="实验 8-5 自我修改流水线")
    parser.add_argument("--generator", choices=("deterministic", "llm"), default="deterministic")
    parser.add_argument("--model", help="真实 LLM 模型；默认使用 LLM_MODEL 或 gpt-5.6")
    args = parser.parse_args()
    trajectories = json.loads((ROOT / "failure_trajectories.json").read_text(encoding="utf-8"))
    stable_path = ROOT / "stable" / "retry_policy.py"
    stable_source = stable_path.read_text(encoding="utf-8")

    diagnosis = diagnose(trajectories)
    if args.generator == "llm":
        from llm_generator import generate_with_openai
        candidate = generate_with_openai(stable_source, diagnosis, args.model)
    else:
        candidate = generate_candidate(stable_source, diagnosis)
    checks = validate_candidate(candidate["source"], trajectories, stable_source)
    manifest = release_manifest(stable_source, candidate, diagnosis, checks)

    write_candidate(candidate["source"], ROOT / "output" / "candidate" / "retry_policy.py")
    (ROOT / "output" / "release_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"实验 8-5：轨迹触发的自我修改（生成器={args.generator}）\n")
    print("诊断目标：", diagnosis["target"])
    print("源案例：", ", ".join(diagnosis["source_case_ids"]))
    print("\n候选差异：\n")
    print(candidate["diff"])
    print("检查：", checks)
    print("决策：", manifest["decision"])
    print("稳定文件未修改：", stable_path.read_text(encoding="utf-8") == stable_source)
    print("回滚版本：", manifest["rollback_version"])


if __name__ == "__main__":
    main()
