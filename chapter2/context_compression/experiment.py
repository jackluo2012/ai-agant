"""
上下文压缩策略对比实验
=======================

自动化对比脚本 - 运行所有策略并生成对比报告

使用方法:
    python experiment.py                          # 运行所有 6 种策略
    python experiment.py -s context_aware         # 仅运行上下文感知策略
    python experiment.py -s individual combined    # 运行两种非上下文感知策略
    python experiment.py -m kimi-k3 -o results/run.json
    python experiment.py --list-strategies
"""

import argparse
import sys
import os
import json
import time
from datetime import datetime
from typing import List, Dict, Any

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
    """解析策略名称（支持别名）"""
    return STRATEGY_ALIASES.get(name, name)


def print_banner():
    """打印程序横幅"""
    print("\n" + "="*70)
    print("    上下文压缩策略对比实验")
    print("="*70 + "\n")


def print_strategy_list():
    """打印可用策略列表"""
    print("\n可用的压缩策略：")
    print("-" * 50)
    for i, strategy in enumerate(CompressionStrategy, 1):
        print(f"  {i}. {strategy.value:45s}")
    print("-" * 50 + "\n")


def run_single_experiment(
    strategy: CompressionStrategy,
    max_iterations: int = 15,
    enable_streaming: bool = False
) -> Dict[str, Any]:
    """
    运行单个策略的实验

    Args:
        strategy: 压缩策略
        max_iterations: 最大迭代次数
        enable_streaming: 启用流式输出

    Returns:
        实验结果字典
    """
    print(f"\n{'='*70}")
    print(f"正在运行策略: {strategy.value}")
    print(f"{'='*70}\n")

    start_time = time.time()

    try:
        # 创建 Agent
        agent = ResearchAgent(
            compression_strategy=strategy,
            enable_streaming=enable_streaming
        )

        # 执行研究
        result = agent.execute_research(max_iterations=max_iterations)

        # 添加策略信息
        result['strategy_name'] = strategy.value
        result['experiment_timestamp'] = datetime.now().isoformat()

        return result

    except Exception as e:
        return {
            'strategy_name': strategy.value,
            'error': str(e),
            'success': False,
            'experiment_timestamp': datetime.now().isoformat()
        }


def calculate_compression_stats(trajectory) -> Dict[str, Any]:
    """
    计算压缩统计信息

    Args:
        trajectory: Agent 执行轨迹

    Returns:
        压缩统计字典
    """
    compressed_calls = [c for c in trajectory.tool_calls if c.compressed_result]

    if not compressed_calls:
        return {
            'compressed_calls': 0,
            'original_chars': 0,
            'compressed_chars': 0,
            'compression_ratio': 0
        }

    original_total = sum(c.compressed_result.original_length for c in compressed_calls)
    compressed_total = sum(c.compressed_result.compressed_length for c in compressed_calls)
    ratio = (compressed_total / original_total * 100) if original_total > 0 else 0

    return {
        'compressed_calls': len(compressed_calls),
        'original_chars': original_total,
        'compressed_chars': compressed_total,
        'compression_ratio': ratio
    }


def print_comparison_table(results: List[Dict[str, Any]]):
    """
    打印对比表格

    Args:
        results: 实验结果列表
    """
    print("\n" + "="*100)
    print(" " * 35 + "实验结果对比表")
    print("="*100)
    print(
        f"{'#':<4} {'策略':<28} {'成功':<8} {'迭代':<8} {'Tokens':<12} {'压缩率':<10} {'溢出':<8} {'耗时(秒)':<10}"
    )
    print("-"*100)

    for i, result in enumerate(results, 1):
        trajectory = result.get('trajectory')
        strategy = result.get('strategy_name', 'unknown')

        # 获取状态
        success = "✅" if result.get('success') else "❌"
        if result.get('error'):
            success = f"❌ {result.get('error', '')[:30]}"

        # 获取迭代次数
        iterations = result.get('iterations', 'N/A')

        # 获取 token 数
        tokens = f"{trajectory.total_tokens_used:,}" if trajectory else 'N/A'

        # 获取压缩率
        stats = calculate_compression_stats(trajectory) if trajectory else {}
        ratio = f"{stats.get('compression_ratio', 0):.1f}%" if stats else 'N/A'

        # 获取溢出次数
        overflows = trajectory.context_overflows if trajectory else 0

        # 获取耗时
        exec_time = result.get('execution_time', 0)
        time_str = f"{exec_time:.0f}" if exec_time else 'N/A'

        print(
            f"{i:<4} {strategy:<28} {success:<8} {iterations:<8} {tokens:<12} {ratio:<10} {overflows:<8} {time_str:<10}"
        )

    print("="*100 + "\n")


def save_results(results: List[Dict[str, Any]], output_file: str = None):
    """
    保存实验结果到 JSON 文件

    Args:
        results: 实验结果列表
        output_file: 输出文件路径
    """
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"results/experiment_{timestamp}.json"

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # 准备可序列化的数据
    serializable_results = []
    for result in results:
        data = {
            "strategy": result.get("strategy_name"),
            "timestamp": result.get("experiment_timestamp"),
            "success": result.get("success", False),
            "iterations": result.get("iterations"),
            "execution_time": result.get("execution_time"),
            "error": result.get("error"),
            "final_answer": result.get("final_answer"),
            "compression_stats": calculate_compression_stats(result.get("trajectory")) if result.get("trajectory") else {},
            "trajectory": {
                "tool_calls_count": len(result.get("trajectory", {}).tool_calls) if result.get("trajectory") else 0,
                "total_tokens_used": result.get("trajectory", {}).total_tokens_used if result.get("trajectory") else 0,
                "prompt_tokens_used": result.get("trajectory", {}).prompt_tokens_used if result.get("trajectory") else 0,
                "completion_tokens_used": result.get("trajectory", {}).completion_tokens_used if result.get("trajectory") else 0,
                "last_prompt_tokens": result.get("trajectory", {}).last_prompt_tokens if result.get("trajectory") else 0,
                "context_overflows": result.get("trajectory", {}).context_overflows if result.get("trajectory") else 0,
            }
        }
        serializable_results.append(data)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "experiment_timestamp": datetime.now().isoformat(),
            "results": serializable_results
        }, f, indent=2, ensure_ascii=False)

    print(f"📁 结果已保存到: {output_file}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='上下文压缩策略对比实验',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '-s', '--strategy',
        type=str,
        nargs='+',
        help='要运行的策略（可多个，默认全部）。支持别名：context_aware, individual, combined, citations, windowed 等'
    )

    parser.add_argument(
        '-n', '--max-iterations',
        type=int,
        default=15,
        help='每个策略的最大迭代次数（默认：15）'
    )

    parser.add_argument(
        '--streaming',
        action='store_true',
        help='启用流式输出'
    )

    parser.add_argument(
        '-o', '--output',
        type=str,
        help='输出 JSON 文件路径'
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

    # 打印配置
    Config.print_config()

    # 列出策略
    if args.list_strategies:
        print_strategy_list()
        return

    # 确定要运行的策略
    if args.strategy:
        strategies = []
        for s in args.strategy:
            strategy_name = resolve_strategy_name(s)
            try:
                strategies.append(CompressionStrategy(strategy_name))
            except ValueError:
                print(f"❌ 无效的策略: {s}")
                print(f"可用策略: {', '.join(STRATEGY_ALIASES.keys())}")
                sys.exit(1)
    else:
        strategies = list(CompressionStrategy)

    print(f"将运行 {len(strategies)} 个策略的对比实验\n")

    # 运行实验
    results = []
    for strategy in strategies:
        result = run_single_experiment(
            strategy=strategy,
            max_iterations=args.max_iterations,
            enable_streaming=args.streaming
        )
        results.append(result)

        # 策略之间短暂暂停
        time.sleep(1)

    # 打印对比表格
    print_comparison_table(results)

    # 保存结果
    save_results(results, args.output)

    # 打印总结
    print("\n实验总结：")
    print("-" * 50)

    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]

    print(f"成功策略: {len(successful)}/{len(results)}")
    print(f"失败策略: {len(failed)}/{len(results)}")

    if successful:
        best_token = min(successful, key=lambda r: r.get('trajectory', {}).total_tokens_used if r.get('trajectory') else float('inf'))
        print(f"最省 Token 策略: {best_token.get('strategy_name')} ({best_token.get('trajectory', {}).total_tokens_used if best_token.get('trajectory') else 0:,} tokens)")

        fastest = min(successful, key=lambda r: r.get('execution_time', float('inf')))
        print(f"最快策略: {fastest.get('strategy_name')} ({fastest.get('execution_time', 0):.1f} 秒)")

    print("-" * 50 + "\n")


if __name__ == "__main__":
    main()
