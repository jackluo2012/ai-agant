"""使用参考或真实 LLM 支持的代理运行实验 8-7。"""

from __future__ import annotations

import sys
import os

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

import argparse
import json
from pathlib import Path

from agent import OpenAILongitudinalAgent, ReferenceAgent
from harness import LongitudinalEvaluator


ROOT = Path(__file__).parent


def load_tasks():
    """
    加载任务数据集

    Returns:
        任务字典列表
    """
    return json.loads((ROOT / "dataset.json").read_text(encoding="utf-8"))["tasks"]


def main() -> None:
    """主函数入口"""
    parser = argparse.ArgumentParser(description="实验 8-7：纵向持续演化评估")
    parser.add_argument("--profile", choices=("evolving", "append_only", "static", "llm", "all"), default="all",
                        help="代理配置类型")
    parser.add_argument("--model", help="--profile llm 使用的模型；默认使用 LLM_MODEL 或配置文件中的模型")
    parser.add_argument("--output", help="可选的 JSON 报告输出路径")
    args = parser.parse_args()

    profiles = ("evolving", "append_only", "static") if args.profile == "all" else (args.profile,)
    reports = []

    for profile in profiles:
        # 创建代理实例
        if profile == "llm":
            agent = OpenAILongitudinalAgent(args.model)
        else:
            agent = ReferenceAgent(profile)
        # 运行评估
        reports.append(LongitudinalEvaluator().run(agent, load_tasks()))

    # 打印结果表头
    print("实验 8-7：代理是否持续演化？\n")
    print(f"{'配置':<14} {'学习':>7} {'迁移':>9} {'变更':>8} {'保留':>8} "
          f"{'安全':>8} {'负迁移':>9} {'tokens':>8} {'存储':>9}")

    # 打印各配置的结果
    for report in reports:
        phases = report["phase_accuracy"]
        print(
            f"{report['profile']:<14} {phases['learning']:>7.3f} {phases['transfer']:>9.3f} "
            f"{phases['change']:>8.3f} {report['retention_rate']:>8.3f} "
            f"{report['safety_rubric_pass_rate']:>8.3f} {report['negative_transfer_rate']:>9.3f} "
            f"{report['cost']['tokens']:>8} {report['cost']['storage_bytes']:>9}"
        )

    # 打印演化代理的学习曲线
    evolving = next((item for item in reports if item["profile"] == "evolving"), None)
    if evolving:
        print("\n演化代理学习曲线：")
        print(" -> ".join(
            f"{point['task_id']}:{point['cumulative_accuracy']:.2f}"
            for point in evolving["learning_curve"]
        ))
        print("变更信号后恢复所需任务数：", evolving["adaptation"]["tasks_after_change_signal_to_recover"])

    # 保存报告
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
