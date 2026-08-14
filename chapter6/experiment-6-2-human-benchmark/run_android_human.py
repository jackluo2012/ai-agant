#!/usr/bin/env python3
"""
使用上游 HumanAgent 和评估器运行一个固定的 AndroidWorld 任务。

此脚本用于 AndroidWorld 基准测试，加载 UIAutomator 环境配置，
运行指定任务，并输出评估结果。
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def load_uiautomator_env(args):
    """
    加载 UIAutomator 环境配置

    Args:
        args: 命令行参数，包含控制台端口、gRPC 端口和 ADB 路径

    Returns:
        配置完成的 AndroidEnv 环境
    """
    from android_env import loader
    from android_env.components import config_classes
    from android_world.env import android_world_controller
    from android_world.env import env_launcher
    from android_world.env import interface

    # 创建 Android 环境配置
    config = config_classes.AndroidEnvConfig(
        task=config_classes.FilesystemTaskConfig(
            path=android_world_controller._write_default_task_proto()
        ),
        simulator=config_classes.EmulatorConfig(
            emulator_launcher=config_classes.EmulatorLauncherConfig(
                emulator_console_port=args.console_port,
                adb_port=args.console_port + 1,
                grpc_port=args.grpc_port,
            ),
            adb_controller=config_classes.AdbControllerConfig(adb_path=args.adb_path),
        ),
    )
    # 加载基础环境
    base_env = loader.load(config)
    # 创建 AndroidWorld 控制器，使用 UIAUTOMATOR 方法
    controller = android_world_controller.AndroidWorldController(
        base_env,
        a11y_method=android_world_controller.A11yMethod.UIAUTOMATOR,
        install_a11y_forwarding_app=False,
    )
    # 创建异步环境并设置
    env = interface.AsyncAndroidEnv(controller)
    env_launcher.setup_env(env, emulator_setup=False, freeze_datetime=False)
    return env


def main() -> int:
    """
    主函数：解析命令行参数并运行 AndroidWorld 任务

    Returns:
        int: 0 表示成功，1 表示失败
    """
    parser = argparse.ArgumentParser(
        description="使用上游 HumanAgent 运行 AndroidWorld 基准测试任务"
    )
    parser.add_argument("--checkout", type=Path, required=True,
        help="AndroidWorld 代码仓库路径")
    parser.add_argument("--task", required=True,
        help="要运行的任务 ID")
    parser.add_argument("--tier", choices=("easy", "medium", "hard"), required=True,
        help="任务难度级别")
    parser.add_argument("--seed", type=int, required=True,
        help="随机种子")
    parser.add_argument("--output", type=Path, required=True,
        help="结果输出文件路径")
    parser.add_argument("--adb-path", default="/opt/android/platform-tools/adb",
        help="ADB 可执行文件路径")
    parser.add_argument("--console-port", type=int, default=5554,
        help="模拟器控制台端口")
    parser.add_argument("--grpc-port", type=int, default=8554,
        help="gRPC 服务端口")
    args = parser.parse_args()

    # 将 AndroidWorld 代码路径添加到系统路径
    sys.path.insert(0, str(args.checkout))
    from android_world import registry
    from android_world import suite_utils
    from android_world.agents import human_agent

    # 加载 UIAutomator 环境
    env = load_uiautomator_env(args)
    # 创建任务注册表
    task_registry = registry.TaskRegistry()
    # 创建测试套件
    suite = suite_utils.create_suite(
        task_registry.get_registry(task_registry.ANDROID_WORLD_FAMILY),
        n_task_combinations=1,
        seed=args.seed,
        tasks=[args.task],
        use_identical_params=True,
    )
    suite.suite_family = task_registry.ANDROID_WORLD_FAMILY
    # 创建人工代理
    agent = human_agent.HumanAgent(env)
    agent.name = "human_agent_codex"
    started = datetime.now(timezone.utc)
    try:
        # 运行测试套件
        episodes = suite_utils.run(suite, agent)
    finally:
        # 确保环境被正确关闭
        env.close()
    finished = datetime.now(timezone.utc)

    # 构建结果字典
    result = {
        "benchmark": "AndroidWorld",
        "operator": "Codex acting as the human operator",
        "task_id": args.task,
        "tier": args.tier,
        "seed": args.seed,
        "source_commit": "0e95d641e244504c22087cc29b013f3b2428a261",
        "observation_compatibility_path": "upstream UIAUTOMATOR controller; task and evaluator unchanged",
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "episodes": episodes,
    }
    # 确保输出目录存在
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # 写入结果文件
    args.output.write_text(json.dumps(result, indent=2, default=str) + "\n")
    # 打印结果到标准输出
    print(json.dumps(result, indent=2, default=str))
    # 返回成功状态
    return 0 if episodes and episodes[0].get("is_successful") == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
