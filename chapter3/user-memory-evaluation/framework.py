"""用户记忆评估的主框架。"""

import os
import yaml
from typing import List, Dict, Optional, Any
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from config import Config
from models import (
    TestCase, ConversationHistory, ConversationMessage,
    EvaluationResult, TestSuite, MessageRole
)
from evaluator import LLMEvaluator, BatchEvaluator


console = Console()


class UserMemoryEvaluationFramework:
    """用于评估 AI 代理用户记忆能力的框架。"""

    def __init__(self, test_cases_dir: Optional[str] = None):
        """
        初始化框架。

        Args:
            test_cases_dir: 包含测试用例 YAML 文件的目录
        """
        self.test_cases_dir = Path(test_cases_dir or Config.TEST_CASES_DIR)
        self.test_suite = None
        self.evaluator = None
        self._load_test_cases()

    def _load_test_cases(self) -> None:
        """从 YAML 文件加载所有测试用例。"""
        test_cases = []

        for category in ["layer1", "layer2", "layer3"]:
            category_dir = self.test_cases_dir / category
            if not category_dir.exists():
                console.print(f"[yellow]警告：类别目录 {category_dir} 不存在[/yellow]")
                continue

            for yaml_file in category_dir.glob("*.yaml"):
                try:
                    test_case = self._load_single_test_case(yaml_file)
                    if test_case and test_case.validate():
                        test_cases.append(test_case)
                    else:
                        console.print(f"[red]无效的测试用例：{yaml_file}[/red]")
                except Exception as e:
                    console.print(f"[red]加载 {yaml_file} 时出错：{e}[/red]")

        self.test_suite = TestSuite(
            name="User Memory Evaluation Suite",
            version="1.0.0",
            test_cases=test_cases
        )

        console.print(f"[green]已加载 {len(test_cases)} 个测试用例[/green]")
    
    def _load_single_test_case(self, yaml_file: Path) -> Optional[TestCase]:
        """从 YAML 文件加载单个测试用例。"""
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data:
            return None

        # 解析对话历史
        conversation_histories = []
        for conv_data in data.get('conversation_histories', []):
            messages = []
            # 处理 'messages' 和 'conversation' 字段以保持向后兼容
            msg_list = conv_data.get('messages') or conv_data.get('conversation', [])
            for msg in msg_list:
                # 处理字典格式和简单格式
                if isinstance(msg, dict) and 'role' in msg and 'content' in msg:
                    messages.append(ConversationMessage(
                        role=MessageRole(msg['role']),
                        content=msg['content']
                    ))
                elif isinstance(msg, dict):
                    # 处理类似 {user: "...", representative: "..."} 的格式
                    for role, content in msg.items():
                        if role in ['user', 'assistant', 'representative', 'agent']:
                            # 规范化角色名称
                            role_name = 'assistant' if role in ['representative', 'agent'] else role
                            messages.append(ConversationMessage(
                                role=MessageRole(role_name),
                                content=content
                            ))

            # 处理 'id' 和 'conversation_id' 字段以保持向后兼容
            conv_id = conv_data.get('conversation_id') or conv_data.get('id')
            if not conv_id:
                raise KeyError("对话必须具有 'conversation_id' 或 'id' 字段")

            conversation_histories.append(ConversationHistory(
                conversation_id=conv_id,
                timestamp=conv_data['timestamp'],
                messages=messages,
                metadata=conv_data.get('metadata')
            ))

        # 解析评估标准 - 现在只是一个文本字段
        evaluation_criteria = data.get('evaluation_criteria', '')
        if isinstance(evaluation_criteria, dict):
            # 处理包含 description、required_information 等的旧格式
            # 转换为文本格式以保持向后兼容
            criteria_text = evaluation_criteria.get('description', '')
            if 'required_information' in evaluation_criteria:
                criteria_text += "\n\n必需信息：\n"
                for info in evaluation_criteria['required_information']:
                    criteria_text += f"- {info}\n"
            if 'success_indicators' in evaluation_criteria:
                criteria_text += "\n成功指标：\n"
                for indicator in evaluation_criteria['success_indicators']:
                    criteria_text += f"- {indicator}\n"
            if 'failure_indicators' in evaluation_criteria and evaluation_criteria['failure_indicators']:
                criteria_text += "\n失败指标：\n"
                for indicator in evaluation_criteria['failure_indicators']:
                    criteria_text += f"- {indicator}\n"
            evaluation_criteria = criteria_text

        return TestCase(
            test_id=data['test_id'],
            category=data['category'],
            title=data['title'],
            description=data['description'],
            conversation_histories=conversation_histories,
            user_question=data['user_question'],
            evaluation_criteria=evaluation_criteria,
            expected_behavior=data.get('expected_behavior')  # 可选字段
        )
    
    def list_test_cases(self, category: Optional[str] = None) -> List[TestCase]:
        """
        列出所有可用的测试用例。

        Args:
            category: 可选的类别过滤器（layer1、layer2、layer3）

        Returns:
            按 test_id 排序的测试用例列表
        """
        if not self.test_suite:
            return []

        if category:
            test_cases = self.test_suite.get_by_category(category)
        else:
            test_cases = self.test_suite.test_cases

        # 按 test_id 排序返回
        return sorted(test_cases, key=lambda tc: tc.test_id)

    def get_test_case(self, test_id: str) -> Optional[TestCase]:
        """
        通过 ID 获取特定测试用例。

        Args:
            test_id: 测试用例 ID

        Returns:
            TestCase 或 None（如果未找到）
        """
        if not self.test_suite:
            return None
        return self.test_suite.get_by_id(test_id)

    def get_conversation_histories(self, test_id: str) -> List[ConversationHistory]:
        """
        获取测试用例的对话历史。

        Args:
            test_id: 测试用例 ID

        Returns:
            对话历史列表
        """
        test_case = self.get_test_case(test_id)
        if not test_case:
            return []
        return test_case.conversation_histories

    def get_user_question(self, test_id: str) -> Optional[str]:
        """
        获取测试用例的用户问题。

        Args:
            test_id: 测试用例 ID

        Returns:
            用户问题字符串或 None
        """
        test_case = self.get_test_case(test_id)
        if not test_case:
            return None
        return test_case.user_question

    def submit_and_evaluate(
        self,
        test_id: str,
        agent_response: str,
        extracted_memory: Optional[str] = None,
        evaluator_type: Optional[str] = None
    ) -> Optional[EvaluationResult]:
        """
        提交代理的响应并获取评估结果。

        Args:
            test_id: 测试用例 ID
            agent_response: 代理对用户问题的响应
            extracted_memory: 可选的代理提取的记忆
            evaluator_type: 可选的评估器类型（默认使用配置）

        Returns:
            EvaluationResult 或 None（如果未找到测试用例）
        """
        test_case = self.get_test_case(test_id)
        if not test_case:
            console.print(f"[red]未找到测试用例 {test_id}[/red]")
            return None

        if not self.evaluator or evaluator_type:
            self.evaluator = LLMEvaluator(evaluator_type)

        result = self.evaluator.evaluate(
            test_case,
            agent_response,
            extracted_memory
        )

        return result

    def evaluate_batch(
        self,
        agent_responses: Dict[str, str],
        extracted_memories: Optional[Dict[str, str]] = None,
        category: Optional[str] = None,
        evaluator_type: Optional[str] = None,
        model: Optional[str] = None
    ) -> Dict[str, EvaluationResult]:
        """
        批量评估多个测试用例。

        Args:
            agent_responses: test_id 到代理响应的字典映射
            extracted_memories: 可选的 test_id 到提取记忆的字典映射
            category: 可选的类别过滤器
            evaluator_type: 可选的评估器类型
            model: 可选的模型名称覆盖（用于评委 LLM）

        Returns:
            test_id 到评估结果的字典映射
        """
        batch_evaluator = BatchEvaluator(evaluator_type, model=model)
        test_cases = self.list_test_cases(category)

        return batch_evaluator.evaluate_test_suite(
            test_cases,
            agent_responses,
            extracted_memories
        )

    def generate_report(
        self,
        results: Dict[str, EvaluationResult],
        output_file: Optional[str] = None
    ) -> str:
        """
        生成评估报告。

        Args:
            results: 评估结果字典
            output_file: 可选的报告保存文件

        Returns:
            报告字符串
        """
        batch_evaluator = BatchEvaluator()
        report = batch_evaluator.generate_report(
            results,
            self.test_suite.test_cases
        )

        if output_file:
            with open(output_file, 'w') as f:
                f.write(report)
            console.print(f"[green]报告已保存到 {output_file}[/green]")

        return report

    def display_test_case_summary(self, show_full_titles: bool = True, by_category: bool = True) -> None:
        """
        显示所有测试用例的摘要。

        Args:
            show_full_titles: 如果为 True，显示完整标题而不截断
            by_category: 如果为 True，按类别组织显示
        """
        if not self.test_suite:
            console.print("[red]未加载测试用例[/red]")
            return

        if by_category:
            # 按类别显示
            categories = ['layer1', 'layer2', 'layer3']
            for category in categories:
                test_cases = self.test_suite.get_by_category(category)
                if test_cases:
                    # 按 ID 排序测试用例
                    test_cases = sorted(test_cases, key=lambda tc: tc.test_id)
                    console.print(f"\n[bold cyan]{category.upper()}: {len(test_cases)} 个测试用例[/bold cyan]")
                    for tc in test_cases:
                        if show_full_titles:
                            console.print(f"  - {tc.test_id}: {tc.title}")
                        else:
                            title = tc.title[:60] + "..." if len(tc.title) > 60 else tc.title
                            console.print(f"  - {tc.test_id}: {title}")
        else:
            # 以表格形式显示
            table = Table(title="测试用例摘要", show_header=True)
            table.add_column("类别", style="cyan")
            table.add_column("测试 ID", style="magenta")
            table.add_column("标题", style="green")
            table.add_column("对话数", justify="center")
            table.add_column("轮数", justify="center")

            # 按 ID 排序测试用例
            sorted_test_cases = sorted(self.test_suite.test_cases, key=lambda tc: tc.test_id)
            for test_case in sorted_test_cases:
                total_rounds = sum(h.rounds for h in test_case.conversation_histories)
                title = test_case.title if show_full_titles else (test_case.title[:40] + "..." if len(test_case.title) > 40 else test_case.title)
                table.add_row(
                    test_case.category,
                    test_case.test_id,
                    title,
                    str(len(test_case.conversation_histories)),
                    str(total_rounds)
                )

            console.print(table)

    def display_test_case_detail(self, test_id: str) -> None:
        """显示测试用例的详细信息。"""
        test_case = self.get_test_case(test_id)
        if not test_case:
            console.print(f"[red]未找到测试用例 {test_id}[/red]")
            return

        panel_content = f"""[bold cyan]标题：[/bold cyan] {test_case.title}
[bold cyan]类别：[/bold cyan] {test_case.category}
[bold cyan]描述：[/bold cyan] {test_case.description}

[bold yellow]用户问题：[/bold yellow]
{test_case.user_question}"""

        if test_case.expected_behavior:
            panel_content += f"""

[bold yellow]预期行为：[/bold yellow]
{test_case.expected_behavior}"""

        panel_content += f"""

[bold yellow]评估标准：[/bold yellow]
{test_case.evaluation_criteria}

[bold cyan]对话历史：[/bold cyan]
  数量：{len(test_case.conversation_histories)}
  总轮数：{sum(h.rounds for h in test_case.conversation_histories)}
"""

        console.print(Panel(panel_content, title=f"测试用例：{test_id}", expand=False))


class TestCaseExporter:
    """将测试用例导出为不同格式。"""

    @staticmethod
    def export_to_json(test_cases: List[TestCase], output_file: str) -> None:
        """将测试用例导出为 JSON 格式。"""
        import json
        data = []
        for tc in test_cases:
            tc_dict = tc.model_dump()
            # 将消息对象转换为字典
            for hist in tc_dict['conversation_histories']:
                hist['messages'] = [
                    {'role': msg['role'], 'content': msg['content']}
                    for msg in hist['messages']
                ]
            data.append(tc_dict)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def export_to_markdown(test_cases: List[TestCase], output_file: str) -> None:
        """将测试用例导出为 Markdown 格式。"""
        content = "# 用户记忆评估测试用例\n\n"

        for category in ["layer1", "layer2", "layer3"]:
            category_cases = [tc for tc in test_cases if tc.category == category]
            if not category_cases:
                continue

            # 按 test_id 排序以保持一致的顺序
            category_cases = sorted(category_cases, key=lambda tc: tc.test_id)

            content += f"## {category.upper()}\n\n"
            for tc in category_cases:
                content += f"### {tc.test_id}: {tc.title}\n\n"
                content += f"**描述：** {tc.description}\n\n"
                content += f"**用户问题：** {tc.user_question}\n\n"
                if tc.expected_behavior:
                    content += f"**预期行为：** {tc.expected_behavior}\n\n"
                content += f"**对话数：** {len(tc.conversation_histories)} "
                content += f"（总计 {sum(h.rounds for h in tc.conversation_histories)} 轮）\n\n"
                content += "---\n\n"

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
