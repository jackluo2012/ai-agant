"""
状态栏 Agent 主入口
==================

支持命令行任务执行和交互模式
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path

# 导入 Agent 核心模块
from agent import StatusBarAgent, SystemHintConfig
from config import AgentConfig, get_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_section(title: str):
    """打印格式化的章节标题"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)


def print_result(result: dict):
    """打印格式化的结果"""
    if result.get('success'):
        print("\n✅ 任务执行成功！")
        if result.get('final_answer'):
            print("\n📝 最终答案:")
            print("-"*40)
            print(result['final_answer'])
    else:
        print("\n❌ 任务执行失败！")
        if result.get('error'):
            print(f"错误: {result['error']}")

    print(f"\n📊 统计信息:")
    print(f"  - 迭代次数: {result.get('iterations', 0)}")
    print(f"  - 工具调用: {len(result.get('tool_calls', []))}")

    if result.get('trajectory_file'):
        print(f"\n💾 轨迹已保存到: {result['trajectory_file']}")

    if result.get('todo_list'):
        print(f"\n📋 最终 TODO 列表:")
        for item in result['todo_list']:
            status_emoji = {
                'pending': '⏳',
                'in_progress': '🔄',
                'completed': '✅',
                'cancelled': '❌'
            }.get(item['status'], '❓')
            print(f"  [{item['id']}] {status_emoji} {item['content']} ({item['status']})")

    # 显示工具调用摘要
    if result.get('tool_calls'):
        print(f"\n🔧 工具调用摘要:")
        tool_summary = {}
        for call in result['tool_calls']:
            tool_name = call.tool_name
            if tool_name not in tool_summary:
                tool_summary[tool_name] = {
                    'count': 0,
                    'success': 0,
                    'failed': 0
                }
            tool_summary[tool_name]['count'] += 1
            if call.error:
                tool_summary[tool_name]['failed'] += 1
            else:
                tool_summary[tool_name]['success'] += 1

        for tool_name, stats in tool_summary.items():
            print(f"  - {tool_name}: {stats['count']} 次调用 "
                  f"({stats['success']} 成功, {stats['failed']} 失败)")


def get_sample_task() -> str:
    """获取示例任务"""
    return """分析当前目录的项目结构，创建一个项目分析报告。

请：
1. 读取当前目录的 README.md 文件
2. 列出主要文件和目录
3. 分析项目结构和用途
4. 创建一个 project_analysis.md 文件，包含你的分析结果
"""


def execute_single_task(task: str, config: SystemHintConfig = None, verbose: bool = False,
                       provider: str = None, model: str = None, base_url: str = None, api_key: str = None):
    """使用 Agent 执行单个任务"""
    # 从环境变量或参数获取配置
    if not api_key:
        api_key = os.getenv("API_KEY") or os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not provider:
        provider = os.getenv("LLM_PROVIDER", "kimi")
    if not model:
        model = os.getenv("LLM_MODEL")
    if not base_url:
        base_url = os.getenv("BASE_URL")

    if not api_key:
        print("❌ 错误: 请设置 API 密钥")
        print("   export API_KEY='your-api-key-here'")
        print("   或 export KIMI_API_KEY='your-kimi-key'")
        print("   （如果只想离线查看状态栏效果，请运行 python main.py --mode preview）")
        return

    print_section("执行单任务模式")

    print(f"\n📋 任务:")
    print("-"*40)
    print(task)
    print("-"*40)

    # 显示配置信息
    print(f"\n⚙️  配置:")
    print(f"  - 提供商: {provider}")
    print(f"  - 模型: {model or '默认'}")
    if base_url:
        print(f"  - API: {base_url}")

    # 创建 Agent
    agent = StatusBarAgent(
        api_key=api_key,
        provider=provider,
        model=model,
        base_url=base_url,
        config=config or SystemHintConfig(),
        verbose=verbose
    )

    # 执行任务
    print("\n🚀 开始执行任务...\n")
    result = agent.execute_task(task, max_iterations=20)

    # 打印结果
    print_result(result)


def run_interactive_mode(config: SystemHintConfig = None, verbose: bool = False,
                         provider: str = None, model: str = None, base_url: str = None, api_key: str = None):
    """运行交互模式"""
    # 从环境变量或参数获取配置
    if not api_key:
        api_key = os.getenv("API_KEY") or os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not provider:
        provider = os.getenv("LLM_PROVIDER", "kimi")
    if not model:
        model = os.getenv("LLM_MODEL")
    if not base_url:
        base_url = os.getenv("BASE_URL")

    if not api_key:
        print("❌ 错误: 请设置 API 密钥")
        print("   export API_KEY='your-api-key-here'")
        return

    print_section("交互模式")

    # 显示配置信息
    print(f"\n⚙️  配置:")
    print(f"  - 提供商: {provider}")
    print(f"  - 模型: {model or '默认'}")
    if base_url:
        print(f"  - API: {base_url}")

    # 创建 Agent
    agent = StatusBarAgent(
        api_key=api_key,
        provider=provider,
        model=model,
        base_url=base_url,
        config=config or SystemHintConfig(),
        verbose=verbose
    )

    print("\n💡 提示: 输入 'quit' 或 'exit' 退出，输入 'reset' 重置 Agent 状态")
    print("-"*40)

    while True:
        try:
            user_input = input("\n🔹 请输入任务: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 再见！")
                break

            if user_input.lower() == 'reset':
                agent.reset()
                print("\n🔄 Agent 状态已重置")
                continue

            # 执行任务
            print("\n🚀 开始执行任务...\n")
            result = agent.execute_task(user_input, max_iterations=20)

            # 打印结果
            print_result(result)

            # 如果成功，显示最终答案
            if result.get('success') and result.get('final_answer'):
                print("\n" + "="*40)
                print(result['final_answer'])
                print("="*40)

        except KeyboardInterrupt:
            print("\n\n👋 再见！")
            break
        except Exception as e:
            print(f"\n❌ 错误: {e}")


def run_preview_mode():
    """运行离线预览模式（无需 API 密钥）"""
    print_section("状态栏预览模式")

    print("\n💡 此模式展示状态栏效果，无需 API 密钥\n")

    # 创建一个虚拟配置
    config = SystemHintConfig(
        enable_timestamps=True,
        enable_tool_counter=True,
        enable_todo_list=True,
        enable_detailed_errors=True,
        enable_system_state=True
    )

    # 导入 agent 模块以创建预览
    from agent import StatusBarAgent, TodoItem, TodoStatus

    # 创建虚拟 Agent（仅用于展示）
    print("📋 状态栏组件预览:\n")
    print("-"*40)

    # 模拟系统状态
    print("\n=== 系统状态 ===")
    print(f"当前时间: {datetime.now().strftime(config.timestamp_format)}")
    print(f"当前目录: {os.getcwd()}")
    import platform
    print(f"系统: {platform.system()} ({platform.release()})")
    print(f"Python 版本: {sys.version.split()[0]}")

    # 模拟 TODO 列表
    print("\n=== 当前任务 ===")
    print("TODO 列表:")
    demo_todos = [
        (1, "分析项目结构", "in_progress"),
        (2, "创建分析报告", "pending"),
        (3, "验证结果", "pending")
    ]
    for tid, content, status in demo_todos:
        symbol = {
            'pending': '⏳',
            'in_progress': '🔄',
            'completed': '✅',
            'cancelled': '❌'
        }.get(status, '❓')
        print(f"  [{tid}] {symbol} {content} ({status})")

    print("\n" + "-"*40)
    print("\n💡 状态栏技术说明:")
    print("  1. 时间戳跟踪 - 帮助理解事件时序")
    print("  2. 工具调用计数 - 防止无限循环")
    print("  3. TODO 列表 - 任务进度管理")
    print("  4. 详细错误 - 提供修复建议")
    print("  5. 系统状态 - 环境感知")
    print("\n✅ 预览完成！运行其他模式以体验完整功能。")


def run_demo_mode(config: SystemHintConfig = None, verbose: bool = False,
                  provider: str = None, model: str = None, base_url: str = None, api_key: str = None):
    """运行演示模式"""
    # 从环境变量或参数获取配置
    if not api_key:
        api_key = os.getenv("API_KEY") or os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not provider:
        provider = os.getenv("LLM_PROVIDER", "kimi")
    if not model:
        model = os.getenv("LLM_MODEL")
    if not base_url:
        base_url = os.getenv("BASE_URL")

    if not api_key:
        print("❌ 错误: 请设置 API 密钥")
        print("   export API_KEY='your-api-key-here'")
        return

    print_section("演示模式")

    # 显示配置信息
    print(f"\n⚙️  配置:")
    print(f"  - 提供商: {provider}")
    print(f"  - 模型: {model or '默认'}")
    if base_url:
        print(f"  - API: {base_url}")

    demo_task = """演示状态栏的各项功能。

请执行以下步骤来展示状态栏技术：
1. 创建一个 TODO 列表，包含 3 个任务
2. 将第一个任务标记为 in_progress
3. 创建一个测试文件
4. 读取这个文件
5. 标记任务为 completed
6. 提供最终总结
"""

    print("\n📋 演示任务:")
    print("-"*40)
    print(demo_task)
    print("-"*40)

    # 创建演示配置（启用时间模拟）
    demo_config = SystemHintConfig(
        enable_timestamps=True,
        enable_tool_counter=True,
        enable_todo_list=True,
        enable_detailed_errors=True,
        enable_system_state=True,
        simulate_time_delay=True  # 启用时间模拟
    )

    # 创建 Agent
    agent = StatusBarAgent(
        api_key=api_key,
        provider=provider,
        model=model,
        base_url=base_url,
        config=demo_config,
        verbose=verbose
    )

    # 执行演示任务
    print("\n🚀 开始执行演示任务...\n")
    result = agent.execute_task(demo_task, max_iterations=20)

    # 打印结果
    print_result(result)


def run_comparison_demo(api_key: str = None, provider: str = None, model: str = None, base_url: str = None):
    """运行对比演示：有/无状态栏的效果对比"""
    # 从环境变量或参数获取配置
    if not api_key:
        api_key = os.getenv("API_KEY") or os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not provider:
        provider = os.getenv("LLM_PROVIDER", "kimi")
    if not model:
        model = os.getenv("LLM_MODEL")
    if not base_url:
        base_url = os.getenv("BASE_URL")

    if not api_key:
        print("❌ 错误: 请设置 API 密钥")
        print("   export API_KEY='your-api-key-here'")
        return

    print_section("状态栏效果对比演示")

    # 显示配置信息
    print(f"\n⚙️  配置:")
    print(f"  - 提供商: {provider}")
    print(f"  - 模型: {model or '默认'}")
    if base_url:
        print(f"  - API: {base_url}")

    # 一个容易陷入循环的任务
    comparison_task = """读取 config.py 文件的前 20 行内容。"""

    print("\n📋 对比任务:")
    print("-"*40)
    print(comparison_task)
    print("-"*40)

    input("\n按 Enter 开始测试（禁用状态栏）...")

    # 无状态栏配置
    config_no_hint = SystemHintConfig(
        enable_timestamps=False,
        enable_tool_counter=False,
        enable_todo_list=False,
        enable_detailed_errors=False,
        enable_system_state=False
    )

    print("\n🔻 测试 1: 禁用所有状态栏技术")
    agent1 = StatusBarAgent(
        api_key=api_key,
        provider=provider,
        model=model,
        base_url=base_url,
        config=config_no_hint
    )
    result1 = agent1.execute_task(comparison_task, max_iterations=10)

    print_result(result1)

    input("\n按 Enter 继续测试（启用状态栏）...")

    # 启用状态栏配置
    config_with_hint = SystemHintConfig(
        enable_timestamps=True,
        enable_tool_counter=True,
        enable_todo_list=True,
        enable_detailed_errors=True,
        enable_system_state=True
    )

    print("\n🔺 测试 2: 启用所有状态栏技术")
    agent2 = StatusBarAgent(
        api_key=api_key,
        provider=provider,
        model=model,
        base_url=base_url,
        config=config_with_hint
    )
    result2 = agent2.execute_task(comparison_task, max_iterations=10)

    print_result(result2)

    # 对比结果
    print("\n" + "="*80)
    print("  对比结果摘要")
    print("="*80)
    print(f"\n{'配置':<20} {'迭代次数':<15} {'工具调用':<15} {'成功':<10}")
    print("-"*60)
    print(f"{'无状态栏':<20} {result1.get('iterations', 0):<15} {len(result1.get('tool_calls', [])):<15} {'✅' if result1.get('success') else '❌':<10}")
    print(f"{'有状态栏':<20} {result2.get('iterations', 0):<15} {len(result2.get('tool_calls', [])):<15} {'✅' if result2.get('success') else '❌':<10}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="状态栏增强的 AI Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
运行模式:
  single      执行单个任务
  interactive 交互模式（默认）
  preview     离线预览状态栏效果（无需 API 密钥）
  demo        运行功能演示
  comparison  对比有/无状态栏的效果

示例:
  python main.py --mode preview                              # 预览状态栏效果
  python main.py --mode single --task "分析项目"              # 执行单个任务
  python main.py --mode interactive                           # 交互模式
  python main.py --mode demo                                  # 功能演示
  python main.py --mode comparison                            # 效果对比

  # 使用自定义 LLM
  python main.py --provider custom --base-url "https://your-api.com/v1" --model "your-model"
  python main.py --provider openai --api-key "sk-..." --model "gpt-4o"
  python main.py --provider deepseek --api-key "sk-..." --model "deepseek-chat"
        """
    )

    parser.add_argument(
        '--mode',
        choices=['single', 'interactive', 'preview', 'demo', 'comparison'],
        default='interactive',
        help='运行模式'
    )

    parser.add_argument('--task', help='要执行的任务（单任务模式）')

    parser.add_argument('--provider',
                       help='LLM 提供商 (kimi, moonshot, openai, deepseek, anthropic, custom)。默认从环境变量 LLM_PROVIDER 读取')

    parser.add_argument('--model',
                       help='模型名称。默认从环境变量 LLM_MODEL 读取')

    parser.add_argument('--base-url',
                       help='API 基础 URL (用于自定义提供商)。默认从环境变量 BASE_URL 读取')

    parser.add_argument('--api-key',
                       help='API 密钥。默认从环境变量 API_KEY 读取')

    parser.add_argument('--preset', choices=['full', 'minimal', 'debug', 'demo'],
                       help='配置预设')

    # 功能开关
    parser.add_argument('--no-timestamps', action='store_true', help='禁用时间戳')
    parser.add_argument('--no-counter', action='store_true', help='禁用工具计数器')
    parser.add_argument('--no-todo', action='store_true', help='禁用 TODO 列表')
    parser.add_argument('--no-errors', action='store_true', help='禁用详细错误')
    parser.add_argument('--no-state', action='store_true', help='禁用系统状态')

    parser.add_argument('--verbose', action='store_true', help='详细日志输出')

    args = parser.parse_args()

    # 加载配置
    if args.preset:
        agent_config = get_config(args.preset)
        config = SystemHintConfig(
            enable_timestamps=agent_config.enable_timestamps,
            enable_tool_counter=agent_config.enable_tool_counter,
            enable_todo_list=agent_config.enable_todo_list,
            enable_detailed_errors=agent_config.enable_detailed_errors,
            enable_system_state=agent_config.enable_system_state
        )
    else:
        config = SystemHintConfig()

    # 应用命令行开关
    if args.no_timestamps:
        config.enable_timestamps = False
    if args.no_counter:
        config.enable_tool_counter = False
    if args.no_todo:
        config.enable_todo_list = False
    if args.no_errors:
        config.enable_detailed_errors = False
    if args.no_state:
        config.enable_system_state = False

    # 根据模式运行
    if args.mode == 'preview':
        run_preview_mode()
    elif args.mode == 'single':
        task = args.task or get_sample_task()
        execute_single_task(task, config, args.verbose, args.provider, args.model, args.base_url, args.api_key)
    elif args.mode == 'demo':
        run_demo_mode(config, args.verbose, args.provider, args.model, args.base_url, args.api_key)
    elif args.mode == 'comparison':
        run_comparison_demo(args.api_key, args.provider, args.model, args.base_url)
    else:  # interactive
        run_interactive_mode(config, args.verbose, args.provider, args.model, args.base_url, args.api_key)


if __name__ == "__main__":
    main()

