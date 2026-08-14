"""无需 API 密钥运行实验 8-1。"""

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

from calibration import calibration_report
from verifier import TrajectoryVerifier, diagnostic_utility, scalar_baseline


ROOT = Path(__file__).parent


def main() -> None:
    """
    主函数：运行实验 8-1 演示。

    使用确定性 HeuristicQualityJudge 无需 API 密钥，
    或使用 LLM 评估器进行真实评估。
    """
    parser = argparse.ArgumentParser(description="实验 8-1 轨迹验证器")
    parser.add_argument("--judge", choices=("heuristic", "llm"), default="heuristic",
                        help="评估器类型：heuristic（确定性，无需 API）或 llm（需要 LLM 配置）")
    parser.add_argument("--model", help="LLM 模型名称（可选，默认使用项目配置）")
    args = parser.parse_args()

    # 加载示例轨迹
    trajectories = json.loads((ROOT / "sample_trajectories.json").read_text(encoding="utf-8"))

    if args.judge == "llm":
        from llm_judge import OpenAIQualityJudge
        verifier = TrajectoryVerifier(quality_judge=OpenAIQualityJudge(args.model))
    else:
        verifier = TrajectoryVerifier()

    # 评估所有轨迹
    reports = [verifier.evaluate(item) for item in trajectories]

    print(f"实验 8-1：三层客服轨迹验证器（评估器={args.judge}）\n")

    # 打印每个报告的摘要
    for report in reports:
        failed = [
            item["dimension"] for item in report["dimensions"] if item["verdict"] == "fail"
        ]
        print(f"{report['trajectory_id']:<24} score={report['overall_score']:.3f} "
              f"decision={report['release_recommendation']:<16} failures={failed or ['none']}")

    # 对比标量基线与多维诊断
    scalar = scalar_baseline(reports[1])
    print("\n标量基线：", scalar)
    print("多维诊断效用：", diagnostic_utility(reports[1]))
    print("\n校准报告：")
    print(json.dumps(calibration_report(trajectories, reports), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
