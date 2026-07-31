"""
上下文压缩实验 - 交互式演示
===========================

单策略交互式演示脚本

使用方法:
    python main.py
    python main.py -s context_aware
    python main.py -s citations --no-streaming
"""

import argparse
import sys
import os
import json
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

try:
    from chapter2.context_compression.config import Config
    from chapter2.context_compression.agent import ResearchAgent
    from chapter2.context_compression.compression_strategies import CompressionStrategy
except ImportError:
    # 本地导入
    from config import Config
    from agent import ResearchAgent
    from compression_strategies import CompressionStrategy


def print_banner():
    """打印程序横幅"""
    print("\n" + "="*70)
    print("    上下文压缩策略对比实验 - 交互式演示")
    print("="*70 + "\n")


def print_strategy_list():
    """打印可用策略列表"""
    print("\n可用的压缩策略：")
    print("-" * 50)
    for i, strategy in enumerate(CompressionStrategy, 1):
        print(f"  {i}. {strategy.value:45s}")
    print("-" * 50 + "\n")


# 策略别名映射
STRATEGY_ALIASES = {
    'no_compression': 'no_compression',
    'none': 'no_compression',
    'individual': 'non_context_aware_individual_summary',
    'individual_summary': 'non_context_aware_individual_summary',
    'combined': 'non_context_aware_combined_summary',
    'combined_summary': 'non_context_aware_combined_summary',
    'context_aware': 'context_aware_summary',
    'context_aware_summary': 'context_aware_summary',
    'citations': 'context_aware_with_citations',
    'windowed': 'windowed_context',
    'windowed_context': 'windowed_context',
}


def resolve_strategy_name(name: str) -> str:
    """
    解析策略名称（支持别名）

    Args:
        name: 策略名称或别名

    Returns:
        完整的策略名称
    """
    return STRATEGY_ALIASES.get(name, name)


def get_strategy_choice() -> CompressionStrategy:
    """
    获取用户策略选择

    Returns:
        选择的压缩策略
    """
    strategies = list(CompressionStrategy)

    print("请选择压缩策略：")
    for i, strategy in enumerate(strategies, 1):
        print(f"  {i}. {strategy.value}")

    while True:
        try:
            choice = input(f"\n请输入选项 (1-{len(strategies)}): ").strip()
            index = int(choice) - 1
            if 0 <= index < len(strategies):
                return strategies[index]
            print(f"无效选项，请输入 1-{len(strategies)} 之间的数字")
        except ValueError:
            print("请输入有效的数字")
        except KeyboardInterrupt:
            print("\n\n操作已取消")
            sys.exit(0)


def print_result_summary(result: dict, strategy: CompressionStrategy):
    """
    打印结果摘要

    Args:
        result: 执行结果
        strategy: 使用的策略
    """
    print("\n" + "="*70)
    print("    执行结果摘要")
    print("="*70 + "\n")

    trajectory = result.get('trajectory')

    if result.get('error'):
        print(f"❌ 状态: 失败")
        print(f"📄 错误: {result['error']}")
    else:
        print(f"✅ 状态: 成功")
        print(f"🎯 最终答案: {result.get('final_answer', 'N/A')[:200]}...")

    print(f"\n📊 统计信息:")
    print(f"   策略: {strategy.value}")
    print(f"   迭代次数: {result.get('iterations', 'N/A')}")
    print(f"   执行时间: {result.get('execution_time', 0):.2f} 秒")
    print(f"   工具调用: {len(trajectory.tool_calls) if trajectory else 0}")

    if trajectory:
        print(f"\n🔢 Token 使用:")
        print(f"   总计: {trajectory.total_tokens_used:,}")
        print(f"   Prompt: {trajectory.prompt_tokens_used:,}")
        print(f"   Completion: {trajectory.completion_tokens_used:,}")
        print(f"   最近 Prompt: {trajectory.last_prompt_tokens:,}")
        print(f"   上下文溢出: {trajectory.context_overflows}")

        # 计算压缩统计
        compressed_calls = [c for c in trajectory.tool_calls if c.compressed_result]
        if compressed_calls:
            original_total = sum(c.compressed_result.original_length for c in compressed_calls)
            compressed_total = sum(c.compressed_result.compressed_length for c in compressed_calls)
            ratio = (compressed_total / original_total * 100) if original_total > 0 else 0
            print(f"\n✂️ 压缩统计:")
            print(f"   压缩调用数: {len(compressed_calls)}")
            print(f"   原始大小: {original_total:,} 字符")
            print(f"   压缩后: {compressed_total:,} 字符")
            print(f"   压缩率: {ratio:.1f}%")

    print("\n" + "="*70 + "\n")


def save_result(result: dict, strategy: CompressionStrategy, output_dir: str = "results"):
    """
    保存结果到 JSON 文件

    Args:
        result: 执行结果
        strategy: 使用的策略
        output_dir: 输出目录
    """
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{strategy.value}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)

    # 准备可序列化的数据
    data = {
        "strategy": strategy.value,
        "timestamp": timestamp,
        "success": result.get("success", False),
        "iterations": result.get("iterations"),
        "execution_time": result.get("execution_time"),
        "error": result.get("error"),
        "final_answer": result.get("final_answer"),
        "trajectory": {
            "tool_calls_count": len(result.get("trajectory", {}).tool_calls) if result.get("trajectory") else 0,
            "total_tokens_used": result.get("trajectory", {}).total_tokens_used if result.get("trajectory") else 0,
            "prompt_tokens_used": result.get("trajectory", {}).prompt_tokens_used if result.get("trajectory") else 0,
            "completion_tokens_used": result.get("trajectory", {}).completion_tokens_used if result.get("trajectory") else 0,
            "last_prompt_tokens": result.get("trajectory", {}).last_prompt_tokens if result.get("trajectory") else 0,
            "context_overflows": result.get("trajectory", {}).context_overflows if result.get("trajectory") else 0,
        }
    }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"📁 结果已保存到: {filepath}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='上下文压缩策略对比实验 - 交互式演示',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '-s', '--strategy',
        type=str,
        help='压缩策略（如不指定则交互选择）。支持别名：context_aware, individual, combined, citations, windowed 等'
    )

    parser.add_argument(
        '-n', '--max-iterations',
        type=int,
        default=15,
        help='最大迭代次数（默认：15）'
    )

    parser.add_argument(
        '--no-streaming',
        action='store_true',
        help='禁用流式输出'
    )

    parser.add_argument(
        '-o', '--output',
        action='store_true',
        help='保存结果到文件'
    )

    parser.add_argument(
        '--list-strategies',
        action='store_true',
        help='列出所有可用策略'
    )

    args = parser.parse_args()

    # 初始化配置
    if not Config.validate():
        print("⚠️ 配置验证失败，但可以继续使用模拟数据")

    Config.create_directories()

    # 打印横幅
    print_banner()

    # 列出策略
    if args.list_strategies:
        print_strategy_list()
        return

    # 确定策略
    if args.strategy:
        # 解析策略名称（支持别名）
        strategy_name = resolve_strategy_name(args.strategy)
        try:
            strategy = CompressionStrategy(strategy_name)
            print(f"使用策略: {strategy.value}\n")
        except ValueError:
            print(f"❌ 无效的策略: {args.strategy}")
            print(f"可用策略: {', '.join(STRATEGY_ALIASES.keys())}")
            sys.exit(1)
    else:
        strategy = get_strategy_choice()

    # 启用流式
    enable_streaming = not args.no_streaming

    try:
        # 创建 Agent
        agent = ResearchAgent(
            compression_strategy=strategy,
            enable_streaming=enable_streaming
        )

        # 执行研究
        result = agent.execute_research(max_iterations=args.max_iterations)

        # 打印结果
        print_result_summary(result, strategy)

        # 保存结果
        if args.output:
            save_result(result, strategy)

    except KeyboardInterrupt:
        print("\n\n操作已取消")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
