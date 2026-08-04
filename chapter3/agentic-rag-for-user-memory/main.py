#!/usr/bin/env python3
"""面向用户记忆评估的 Agentic RAG 系统主入口

此脚本提供交互界面用于：
1. 从 user-memory-evaluation 框架加载测试用例
2. 分块和索引对话历史
3. 对选定的测试用例评估 RAG 智能体
"""

import os
import sys

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
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import Config, ChunkingStrategy, IndexMode
from evaluator import UserMemoryEvaluator


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rich 控制台用于更好的输出
console = Console()


class InteractiveRAGEvaluator:
    """RAG 评估系统的交互界面"""

    def __init__(self, config: Optional[Config] = None):
        """初始化交互评估器"""
        self.config = config or Config.from_env()
        self.evaluator = UserMemoryEvaluator(self.config)
        self.test_cases_loaded = False

    def run(self):
        """运行交互式评估会话"""
        console.print(Panel.fit(
            "[bold cyan]面向用户记忆评估的 Agentic RAG 系统[/bold cyan]\n"
            "用于学习 RAG + 用户记忆系统的教学项目",
            border_style="cyan"
        ))

        while True:
            self.show_menu()
            choice = Prompt.ask(
                "选择一个选项",
                choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
                default="1"
            )

            if choice == "1":
                self.load_test_cases()
            elif choice == "2":
                self.view_test_cases()
            elif choice == "3":
                self.configure_settings()
            elif choice == "4":
                self.evaluate_single_test()
            elif choice == "5":
                self.evaluate_category()
            elif choice == "6":
                self.evaluate_all()
            elif choice == "7":
                self.view_results()
            elif choice == "8":
                self.generate_report()
            elif choice == "9":
                self.demo_mode()
            elif choice == "0":
                if Confirm.ask("确定要退出吗？"):
                    console.print("[yellow]再见！[/yellow]")
                    break

    def show_menu(self):
        """显示主菜单"""
        console.print("\n[bold]主菜单：[/bold]")
        console.print("1. 加载测试用例")
        console.print("2. 查看已加载的测试用例")
        console.print("3. 配置设置")
        console.print("4. 评估单个测试用例")
        console.print("5. 按类别评估")
        console.print("6. 评估所有测试用例")
        console.print("7. 查看结果")
        console.print("8. 生成报告")
        console.print("9. 演示模式（快速测试）")
        console.print("0. 退出")

    def load_test_cases(self):
        """从评估框架加载测试用例"""
        console.print("\n[cyan]正在加载测试用例...[/cyan]")

        category = Prompt.ask(
            "选择要加载的类别",
            choices=["all", "layer1", "layer2", "layer3"],
            default="all"
        )

        category_filter = None if category == "all" else category

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("正在加载测试用例...", total=None)
            test_cases = self.evaluator.load_test_cases(category_filter)
            progress.update(task, completed=True)

        self.test_cases_loaded = True
        console.print(f"[green]✓ 已加载 {len(test_cases)} 个测试用例[/green]")

        # 显示摘要
        categories = {}
        for test_id in test_cases:
            tc = self.evaluator.test_cases[test_id]
            cat = tc.category
            categories[cat] = categories.get(cat, 0) + 1

        for cat, count in sorted(categories.items()):
            console.print(f"  {cat}: {count} 个测试用例")

    def view_test_cases(self):
        """查看已加载的测试用例"""
        if not self.test_cases_loaded:
            console.print("[yellow]未加载测试用例。请先加载测试用例。[/yellow]")
            return

        # 创建表格
        table = Table(title="已加载的测试用例")
        table.add_column("#", style="dim", width=4)
        table.add_column("ID", style="cyan")
        table.add_column("类别", style="magenta")
        table.add_column("标题", style="green")
        table.add_column("对话数", justify="right")

        # 排序测试用例以保持一致的编号
        sorted_test_cases = sorted(self.evaluator.test_cases.items())

        for idx, (test_id, test_case) in enumerate(sorted_test_cases, 1):
            table.add_row(
                str(idx),
                test_id,
                test_case.category,
                test_case.title[:50] + "..." if len(test_case.title) > 50 else test_case.title,
                str(len(test_case.conversation_histories))
            )

        console.print(table)

        # 查看详细信息的选项
        if Confirm.ask("\n查看测试用例详细信息？"):
            # 构建测试 ID 列表用于选择
            test_ids_list = list(self.evaluator.test_cases.keys())
            test_ids_list.sort()

            console.print("\n[dim]输入测试 ID 或上表中的索引编号[/dim]")
            user_input = Prompt.ask("选择测试用例")

            # 检查用户输入的是数字（基于表显示的 1 起始索引）
            test_id = None
            if user_input.isdigit():
                idx = int(user_input) - 1
                if 0 <= idx < len(test_ids_list):
                    test_id = test_ids_list[idx]
                else:
                    console.print(f"[red]无效的索引编号：{user_input}[/red]")
                    return
            else:
                test_id = user_input

            if test_id in self.evaluator.test_cases:
                test_case = self.evaluator.test_cases[test_id]
                console.print(Panel(
                    f"[bold]测试用例：{test_case.title}[/bold]\n\n"
                    f"类别：{test_case.category}\n"
                    f"描述：{test_case.description}\n\n"
                    f"[yellow]用户问题：[/yellow]\n{test_case.user_question}\n\n"
                    f"[green]评估标准：[/green]\n{test_case.evaluation_criteria[:200]}...\n\n"
                    f"对话数：{len(test_case.conversation_histories)}"
                    + (f"\n预期行为：{test_case.expected_behavior[:100]}..." if test_case.expected_behavior else ""),
                    title=test_id,
                    border_style="cyan"
                ))
            else:
                console.print(f"[red]未找到测试用例 {test_id}[/red]")

    def configure_settings(self):
        """配置 RAG 和评估设置"""
        console.print("\n[bold]配置设置[/bold]")

        # 显示当前设置
        console.print(f"\n当前设置：")
        console.print(f"  分块策略：{self.config.chunking.strategy}")
        console.print(f"  每块轮数：{self.config.chunking.rounds_per_chunk}")
        console.print(f"  索引模式：{self.config.index.mode}")
        console.print(f"  最大迭代次数：{self.config.evaluation.max_iterations}")

        if Confirm.ask("\n修改设置？"):
            # 分块设置
            if Confirm.ask("修改分块设置？"):
                rounds = Prompt.ask(
                    "每块轮数",
                    default=str(self.config.chunking.rounds_per_chunk)
                )
                self.config.chunking.rounds_per_chunk = int(rounds)

                overlap = Prompt.ask(
                    "重叠轮数",
                    default=str(self.config.chunking.overlap_rounds)
                )
                self.config.chunking.overlap_rounds = int(overlap)

            # 索引设置
            if Confirm.ask("修改索引设置？"):
                mode = Prompt.ask(
                    "索引模式",
                    choices=["dense", "sparse", "hybrid"],
                    default=self.config.index.mode
                )
                self.config.index.mode = IndexMode(mode)

            # 智能体设置
            if Confirm.ask("修改智能体设置？"):
                max_iter = Prompt.ask(
                    "最大迭代次数",
                    default=str(self.config.evaluation.max_iterations)
                )
                self.config.evaluation.max_iterations = int(max_iter)

                self.config.agent.enable_reasoning = Confirm.ask(
                    "启用推理输出？",
                    default=self.config.agent.enable_reasoning
                )

            # 保存配置
            if Confirm.ask("将配置保存到文件？"):
                config_file = Prompt.ask("配置文件路径", default="config.json")
                self.config.save(config_file)
                console.print(f"[green]配置已保存到 {config_file}[/green]")

    def evaluate_single_test(self):
        """评估单个测试用例"""
        if not self.test_cases_loaded:
            console.print("[yellow]未加载测试用例。请先加载测试用例。[/yellow]")
            return

        # 显示可用的测试用例
        console.print("\n[bold]可用测试用例：[/bold]")

        # 按类别分组以便组织
        categories = {}
        for test_id, test_case in self.evaluator.test_cases.items():
            cat = test_case.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append((test_id, test_case.title))

        # 按类别显示测试用例
        test_ids_list = []
        for cat in sorted(categories.keys()):
            console.print(f"\n[cyan]{cat.upper()}：[/cyan]")
            for test_id, title in sorted(categories[cat]):
                test_ids_list.append(test_id)
                # 显示索引编号以便选择
                idx = len(test_ids_list)
                console.print(f"  [{idx}] {test_id}: {title[:60]}...")

        console.print("\n[dim]直接输入测试 ID 或上表中的编号[/dim]")

        # 允许用户输入测试 ID 或编号
        user_input = Prompt.ask("选择测试用例")

        # 检查用户输入的是数字
        test_id = None
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(test_ids_list):
                test_id = test_ids_list[idx]
            else:
                console.print(f"[red]无效的选择编号：{user_input}[/red]")
                return
        else:
            # 用户直接输入测试 ID
            test_id = user_input
            if test_id not in self.evaluator.test_cases:
                console.print(f"[red]未找到测试用例 {test_id}[/red]")
                return

        test_case = self.evaluator.test_cases[test_id]
        console.print(f"\n[cyan]正在评估：{test_case.title}[/cyan]")
        console.print(f"问题：{test_case.user_question}\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("正在处理...", total=None)

            try:
                result = self.evaluator.evaluate_test_case(test_id)
                progress.update(task, completed=True)

                # 显示结果
                status = "✓ 成功" if result.success else "✗ 失败"
                console.print(f"\n[{'green' if result.success else 'red'}]{status}[/{'green' if result.success else 'red'}]")

                console.print("\n智能体答案：")
                console.print(Panel(result.agent_answer, border_style="cyan"))

                console.print("\n评估标准：")
                console.print(Panel(result.evaluation_criteria, border_style="green"))

                # 显示 LLM 评估（如果可用）
                if hasattr(result, 'llm_evaluation') and result.llm_evaluation and 'reward' in result.llm_evaluation:
                    console.print("\nLLM 评估：")
                    llm_eval = result.llm_evaluation
                    eval_color = "green" if llm_eval['passed'] else "red"
                    console.print(f"  [{'green' if llm_eval['passed'] else 'red'}]通过：{'是' if llm_eval['passed'] else '否'}[/{eval_color}]")
                    console.print(f"  奖励分数：{llm_eval['reward']:.3f}/1.000")
                    console.print(f"  推理：{llm_eval.get('reasoning', 'N/A')}")

                    if llm_eval.get('required_info_found'):
                        console.print("\n  必需信息：")
                        for info, found in llm_eval['required_info_found'].items():
                            check = "[green]✓[/green]" if found else "[red]✗[/red]"
                            console.print(f"    {check} {info}")

                console.print(f"\n统计信息：")
                console.print(f"  迭代次数：{result.iterations}")
                console.print(f"  工具调用：{result.tool_calls}")
                console.print(f"  已索引块数：{result.chunk_count}")
                console.print(f"  处理时间：{result.processing_time:.2f}秒")
                console.print(f"  索引时间：{result.indexing_time:.2f}秒")

            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"错误：{e}")

    def evaluate_category(self):
        """评估类别中的所有测试用例"""
        if not self.test_cases_loaded:
            console.print("[yellow]未加载测试用例。请先加载测试用例。[/yellow]")
            return

        # 显示可用类别和计数
        categories_count = {}
        for test_case in self.evaluator.test_cases.values():
            cat = test_case.category
            categories_count[cat] = categories_count.get(cat, 0) + 1

        console.print("\n[bold]可用类别：[/bold]")
        for cat in sorted(categories_count.keys()):
            console.print(f"  {cat}: {categories_count[cat]} 个测试用例")

        category = Prompt.ask(
            "\n选择类别",
            choices=list(sorted(categories_count.keys()))
        )

        # 获取并显示类别中的测试用例
        test_ids = []
        console.print(f"\n[cyan]{category} 中的测试用例：[/cyan]")
        for tid, tc in sorted(self.evaluator.test_cases.items()):
            if tc.category == category:
                test_ids.append(tid)
                console.print(f"  • {tid}: {tc.title[:60]}...")

        console.print(f"\n[cyan]总计：{len(test_ids)} 个测试用例[/cyan]")

        if not Confirm.ask("继续评估？"):
            return

        # 评估
        with Progress(console=console) as progress:
            task = progress.add_task(f"正在评估 {category}...", total=len(test_ids))

            for test_id in test_ids:
                try:
                    self.evaluator.evaluate_test_case(test_id)
                    progress.advance(task)
                except Exception as e:
                    console.print(f"[red]评估 {test_id} 时出错：{e}[/red]")
                    progress.advance(task)

        console.print(f"[green]✓ {category} 评估完成[/green]")
        self.show_category_results(category)

    def evaluate_all(self):
        """评估所有已加载的测试用例"""
        if not self.test_cases_loaded:
            console.print("[yellow]未加载测试用例。请先加载测试用例。[/yellow]")
            return

        total = len(self.evaluator.test_cases)
        console.print(f"\n[cyan]将评估 {total} 个测试用例[/cyan]")

        if not Confirm.ask("继续完整评估？"):
            return

        # 评估所有
        results = self.evaluator.evaluate_batch()

        console.print(f"[green]✓ 已评估 {len(results)} 个测试用例[/green]")

        # 显示摘要
        successful = sum(1 for r in results.values() if r.success)
        console.print(f"成功率：{successful}/{total} ({100*successful/total:.1f}%)")

    def view_results(self):
        """查看评估结果"""
        if not self.evaluator.results:
            console.print("[yellow]没有可用的评估结果[/yellow]")
            return

        # 创建结果表格
        table = Table(title="评估结果")
        table.add_column("测试 ID", style="cyan")
        table.add_column("类别", style="magenta")
        table.add_column("状态", justify="center")
        table.add_column("迭代次数", justify="right")
        table.add_column("工具调用", justify="right")
        table.add_column("时间（秒）", justify="right")

        for test_id, result in sorted(self.evaluator.results.items()):
            test_case = self.evaluator.test_cases.get(test_id)
            category = test_case.category if test_case else "unknown"
            status = "[green]✓[/green]" if result.success else "[red]✗[/red]"

            table.add_row(
                test_id,
                category,
                status,
                str(result.iterations),
                str(result.tool_calls),
                f"{result.processing_time:.2f}"
            )

        console.print(table)

        # 摘要统计
        total = len(self.evaluator.results)
        successful = sum(1 for r in self.evaluator.results.values() if r.success)

        console.print(f"\n[bold]摘要：[/bold]")
        console.print(f"  总计：{total}")
        console.print(f"  成功：{successful} ({100*successful/total:.1f}%)")

        # 查看详细信息的选项
        if Confirm.ask("\n查看详细结果？"):
            test_id = Prompt.ask("输入测试用例 ID")
            if test_id in self.evaluator.results:
                result = self.evaluator.results[test_id]
                console.print(Panel(
                    f"[bold]测试：{test_id}[/bold]\n\n"
                    f"状态：{'成功' if result.success else '失败'}\n"
                    f"迭代次数：{result.iterations}\n"
                    f"工具调用：{result.tool_calls}\n"
                    f"块数：{result.chunk_count}\n"
                    f"处理时间：{result.processing_time:.2f}秒\n"
                    f"索引时间：{result.indexing_time:.2f}秒\n\n"
                    f"[yellow]智能体答案：[/yellow]\n{result.agent_answer[:300]}...",
                    border_style="cyan"
                ))

    def show_category_results(self, category: str):
        """显示特定类别的结果"""
        category_results = {
            tid: r for tid, r in self.evaluator.results.items()
            if tid in self.evaluator.test_cases and
            self.evaluator.test_cases[tid].category == category
        }

        if not category_results:
            console.print(f"[yellow]{category} 没有结果[/yellow]")
            return

        successful = sum(1 for r in category_results.values() if r.success)
        total = len(category_results)

        console.print(f"\n[bold]{category} 结果：[/bold]")
        console.print(f"  成功率：{successful}/{total} ({100*successful/total:.1f}%)")

        # 平均指标
        if total > 0:
            avg_iter = sum(r.iterations for r in category_results.values()) / total
            avg_tools = sum(r.tool_calls for r in category_results.values()) / total
            avg_time = sum(r.processing_time for r in category_results.values()) / total

            console.print(f"  平均迭代次数：{avg_iter:.1f}")
            console.print(f"  平均工具调用：{avg_tools:.1f}")
            console.print(f"  平均时间：{avg_time:.2f}秒")

    def generate_report(self):
        """生成并保存评估报告"""
        if not self.evaluator.results:
            console.print("[yellow]没有可报告的结果[/yellow]")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"results/report_{timestamp}.txt"

        report = self.evaluator.generate_report(report_file)

        console.print(f"[green]✓ 报告已保存到 {report_file}[/green]")

        if Confirm.ask("显示报告？"):
            console.print("\n" + report)

        # 保存 JSON 结果
        if Confirm.ask("将详细结果保存为 JSON？"):
            json_file = f"results/results_{timestamp}.json"
            self.evaluator.save_results(json_file)
            console.print(f"[green]✓ 结果已保存到 {json_file}[/green]")

    def demo_mode(self):
        """运行简单测试用例的快速演示"""
        console.print("\n[cyan]演示模式 - 快速测试[/cyan]")
        console.print("这将运行一个简单的第一层测试用例进行演示。\n")

        # 仅加载第一层测试用例
        if not self.test_cases_loaded:
            console.print("正在加载第一层测试用例...")
            test_cases = self.evaluator.load_test_cases("layer1")
            self.test_cases_loaded = True

        # 获取第一个第一层测试用例
        layer1_tests = [
            tid for tid, tc in self.evaluator.test_cases.items()
            if tc.category == "layer1"
        ]

        if not layer1_tests:
            console.print("[red]没有可用的第一层测试用例[/red]")
            return

        test_id = layer1_tests[0]
        test_case = self.evaluator.test_cases[test_id]

        console.print(f"[bold]演示测试用例：[/bold] {test_case.title}")
        console.print(f"[bold]问题：[/bold] {test_case.user_question}\n")

        if Confirm.ask("运行演示？"):
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("正在运行演示...", total=None)

                try:
                    result = self.evaluator.evaluate_test_case(test_id)
                    progress.update(task, completed=True)

                    # 显示结果
                    console.print("\n[bold green]演示完成！[/bold green]\n")
                    console.print(f"[bold]智能体答案：[/bold]")
                    console.print(Panel(result.agent_answer, border_style="cyan"))

                    console.print(f"\n[bold]性能：[/bold]")
                    console.print(f"  成功：{'是' if result.success else '否'}")
                    console.print(f"  迭代次数：{result.iterations}")
                    console.print(f"  工具调用：{result.tool_calls}")
                    console.print(f"  时间：{result.processing_time:.2f}秒")

                except Exception as e:
                    progress.update(task, completed=True)
                    console.print(f"[red]演示失败：{e}[/red]")


def _apply_cli_overrides(config: Config, args) -> Config:
    """把命令行参数覆盖到配置上（未指定的项保持默认，不改变原有行为）。"""
    if args.index_mode:
        config.index.mode = IndexMode(args.index_mode)
    if args.backend:
        config.index.retrieval_backend = args.backend
    if args.store_path:
        config.index.index_path = args.store_path
    if args.test_cases_dir:
        config.evaluation.test_cases_dir = args.test_cases_dir
    if args.rounds_per_chunk:
        config.chunking.rounds_per_chunk = args.rounds_per_chunk
    if args.top_k:
        config.agent.max_search_results = args.top_k
    return config


def main():
    """主入口点"""
    parser = argparse.ArgumentParser(
        description="实验 3-10 · 智能体化 RAG 用户记忆评估系统",
        epilog=(
            "示例:\n"
            "  python main.py                              # 交互式菜单（默认）\n"
            "  python main.py --mode offline-demo          # 离线对比演示，无需 API / port 4242\n"
            "  python main.py --mode batch --category layer2 --backend local\n"
            "  python main.py --mode batch --test-id layer2_01_multiple_vehicles\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", type=str,
        help="配置文件（JSON）路径"
    )
    parser.add_argument(
        "--mode",
        choices=["interactive", "batch", "demo", "offline-demo"],
        default="interactive",
        help="运行模式：interactive 交互菜单（默认）/ batch 批量评估 / demo 快速演示 / offline-demo 离线检索对比"
    )
    parser.add_argument(
        "--category",
        choices=["layer1", "layer2", "layer3"],
        help="批量模式下要评估的难度层次"
    )
    parser.add_argument(
        "--test-id", type=str,
        help="指定要评估的单个用例 ID"
    )
    parser.add_argument(
        "--query", type=str,
        help="offline-demo 模式下覆盖用例自带的用户问题"
    )
    parser.add_argument(
        "--index-mode", choices=["dense", "sparse", "hybrid"],
        help="检索策略：dense 稠密 / sparse 稀疏(BM25) / hybrid 混合"
    )
    parser.add_argument(
        "--backend", choices=["auto", "local", "pipeline"],
        help="检索后端：auto 自动（默认，pipeline 不可用则本地）/ local 内置离线 BM25 / pipeline 外部 4242 服务"
    )
    parser.add_argument(
        "--top-k", type=int,
        help="每次记忆检索返回的记忆块数量"
    )
    parser.add_argument(
        "--rounds-per-chunk", type=int,
        help="对话历史分块时每块的轮数（默认 20）"
    )
    parser.add_argument(
        "--store-path", type=str,
        help="记忆索引的存储路径前缀（默认 indexes/memory_index）"
    )
    parser.add_argument(
        "--test-cases-dir", type=str,
        help="评估集 test_cases 目录（默认 ../user-memory-evaluation/test_cases）"
    )
    parser.add_argument(
        "--output", type=str,
        help="结果输出文件路径"
    )

    args = parser.parse_args()

    # offline-demo 模式：委托给完全离线的对比演示脚本
    if args.mode == "offline-demo":
        import offline_demo
        demo_args = offline_demo.build_parser().parse_args([])
        if args.test_id:
            demo_args.test_id = args.test_id
        if args.query:
            demo_args.query = args.query
        if args.top_k:
            demo_args.top_k = args.top_k
        if args.rounds_per_chunk:
            demo_args.rounds_per_chunk = args.rounds_per_chunk
        if args.test_cases_dir:
            demo_args.test_cases_dir = args.test_cases_dir
        if args.output:
            demo_args.output = args.output
        offline_demo.run_demo(demo_args)
        return

    # 加载配置
    config = None
    if args.config:
        config = Config.load(args.config)
    else:
        config = Config.from_env()

    # 应用命令行覆盖项
    config = _apply_cli_overrides(config, args)

    if args.mode == "interactive":
        # 交互模式
        evaluator = InteractiveRAGEvaluator(config)
        evaluator.run()

    elif args.mode == "batch":
        # 批量模式
        evaluator = UserMemoryEvaluator(config)

        if args.test_id:
            # 评估单个测试
            evaluator.load_test_cases()
            result = evaluator.evaluate_test_case(args.test_id)
            console.print(f"结果：{'成功' if result.success else '失败'}")
        else:
            # 评估类别或全部
            evaluator.load_test_cases(args.category)
            results = evaluator.evaluate_batch(category=args.category)

            # 生成报告
            report_file = args.output or f"results/report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            report = evaluator.generate_report(report_file)
            console.print(f"报告已保存到 {report_file}")

            # 摘要
            total = len(results)
            successful = sum(1 for r in results.values() if r.success)
            console.print(f"成功率：{successful}/{total} ({100*successful/total:.1f}%)")

    elif args.mode == "demo":
        # 演示模式
        evaluator = InteractiveRAGEvaluator(config)
        evaluator.demo_mode()


if __name__ == "__main__":
    main()
