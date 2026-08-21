"""
演示：具有学习能力的邮件发送

本演示展示代理如何学习发送邮件并复用学习的工作流。
使用 Ethereal Email (ethereal.email) 作为测试邮件服务。
"""

import argparse
import asyncio
import json
import logging
import time
import sys
import os
from dotenv import load_dotenv

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from browser_use import ChatOpenAI, ChatGoogle
from learning_agent import LearningAgent
from llm_factory import make_llm, DEFAULT_MODEL


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

load_dotenv()


# 默认两阶段任务。第一阶段从头开始教授工作流（昂贵、多模态 LLM 循环）；
# 第二阶段用不同参数回放（便宜、无 LLM）。
DEFAULT_LEARNING_TASK = """
前往 https://ethereal.email 并发送一封测试邮件：
- 收件人：test@example.com
- 主题：来自学习代理的问候
- 内容：这是一封由学习代理发送的测试邮件。工作流将被捕获以供将来复用。
"""

DEFAULT_REPLAY_TASK = """
向 another@example.com 发送一封主题为"工作流测试"
、内容为"这封邮件使用学习的工作流发送。不需要 LLM 调用！"的邮件
"""


class EmailDemo:
    """具有学习能力的邮件发送演示。"""

    def __init__(self, llm_model=DEFAULT_MODEL, knowledge_base_path="./email_knowledge",
                 headless=False, max_steps=20, learning_task=None, replay_task=None,
                 output_path=None):
        self.llm_model = llm_model
        self.knowledge_base_path = knowledge_base_path
        self.headless = headless
        self.max_steps = max_steps
        self.learning_task = learning_task or DEFAULT_LEARNING_TASK
        self.replay_task = replay_task or DEFAULT_REPLAY_TASK
        self.output_path = output_path

    async def run_full_demo(self):
        """运行完整的邮件演示，包括学习和回放阶段。"""

        print("=" * 80)
        print("邮件发送演示 - 学习代理")
        print("=" * 80)
        print("\n本演示使用 Ethereal Email (ethereal.email) 进行测试。")
        print("注意：这是一个测试服务 - 邮件不会实际投递。")
        print("=" * 80)

        # 阶段 1：学习
        await self.phase1_learning()

        # 在阶段 2 之前等待
        print("\n⏳ 在回放阶段之前等待 5 秒...")
        await asyncio.sleep(5)

        # 阶段 2：回放
        await self.phase2_replay()

        # 阶段 3：统计
        self.show_statistics()

        # 可选：持久化前后对比以供后续分析
        if self.output_path:
            self.save_results()

    async def phase1_learning(self):
        """阶段 1：学习如何发送邮件。"""

        print("\n" + "📚 阶段 1：学习 - 首个邮件任务 ".ljust(70, "="))
        print("\n代理将从头开始学习如何发送邮件。")
        print("这需要多次 LLM 调用来探索和理解界面。")
        print("-" * 70)

        # 具有详细信息的任务
        task = self.learning_task

        print(f"任务：{task.strip()}")
        print("预期行为：")
        print("  1. 导航到 Ethereal Email")
        print("  2. 创建测试账户（如需要）")
        print("  3. 撰写并发送邮件")
        print("  4. 捕获工作流以供将来复用")

        # 创建学习代理
        agent = LearningAgent(
            task=task,
            llm=self._get_llm(),
            knowledge_base_path=self.knowledge_base_path,
            headless=self.headless
        )

        print("\n🚀 开始学习阶段...")
        start_time = time.time()

        try:
            result = await agent.run(max_steps=self.max_steps)

            elapsed = time.time() - start_time

            print("\n✅ 学习阶段完成！")
            print(f"  📊 结果：")
            print(f"     - 成功：{'✓' if result['success'] else '✗'}")
            print(f"     - 执行时间：{elapsed:.2f} 秒")
            print(f"     - LLM 调用次数：{result['llm_calls']}")
            print(f"     - 工作流已捕获：{'是' if result['success'] else '否'}")

            if result['success']:
                print("\n  💡 工作流成功学习并保存！")
                print("     代理现在可以无需 LLM 调用重复类似任务。")

            # 存储指标以供对比
            self.learning_metrics = {
                'time': elapsed,
                'llm_calls': result['llm_calls'],
                'success': result['success']
            }

        except Exception as e:
            print(f"\n❌ 学习阶段失败：{e}")
            self.learning_metrics = {'time': 0, 'llm_calls': 0, 'success': False}
    
    async def phase2_replay(self):
        """阶段 2：用不同参数回放学习的工作流。"""

        print("\n" + "🚀 阶段 2：回放 - 第二个邮件任务 ".ljust(70, "="))
        print("\n代理将使用不同参数复用学习的工作流。")
        print("这应该更快并且不需要任何 LLM 调用。")
        print("-" * 70)

        # 不同的邮件参数
        task = self.replay_task

        print(f"任务：{task.strip()}")
        print("预期行为：")
        print("  1. 将任务匹配到学习的工作流")
        print("  2. 提取新参数（收件人、主题、内容）")
        print("  3. 用新参数回放工作流")
        print("  4. 无需任何 LLM 调用完成任务")

        # 创建回放代理
        agent = LearningAgent(
            task=task,
            llm=self._get_llm(),
            knowledge_base_path=self.knowledge_base_path,
            headless=self.headless
        )

        print("\n🔄 开始回放阶段...")
        start_time = time.time()

        try:
            result = await agent.run(max_steps=self.max_steps)

            elapsed = time.time() - start_time

            print("\n✅ 回放阶段完成！")
            print(f"  📊 结果：")
            print(f"     - 成功：{'✓' if result['success'] else '✗'}")
            print(f"     - 执行时间：{elapsed:.2f} 秒")
            print(f"     - 工作流已复用：{'是' if result['replay_used'] else '否'}")

            if result['replay_used']:
                # 计算改进
                if hasattr(self, 'learning_metrics') and self.learning_metrics['success']:
                    speedup = self.learning_metrics['time'] / elapsed
                    calls_saved = self.learning_metrics['llm_calls']

                    print(f"\n  🎯 性能改进：")
                    print(f"     - 速度：{speedup:.1f}x 更快")
                    print(f"     - 节省的 LLM 调用：{calls_saved}")
                    print(f"     - 节省的时间：{self.learning_metrics['time'] - elapsed:.1f} 秒")
            else:
                print(f"     - LLM 调用次数：{result.get('llm_calls', 0)}")
                print("\n  ⚠️ 工作流未被复用。任务可能差异太大。")

            # 存储回放指标
            self.replay_metrics = {
                'time': elapsed,
                'replay_used': result['replay_used'],
                'success': result['success']
            }

        except Exception as e:
            print(f"\n❌ 回放阶段失败：{e}")
            self.replay_metrics = {'time': 0, 'replay_used': False, 'success': False}
    
    def show_statistics(self):
        """显示知识库统计信息。"""

        print("\n" + "📊 知识库统计信息 ".ljust(70, "="))

        from learning_agent import KnowledgeBase
        kb = KnowledgeBase(self.knowledge_base_path)
        stats = kb.get_statistics()

        print("\n  当前知识库状态：")
        for key, value in stats.items():
            formatted_key = key.replace('_', ' ').title()
            print(f"     - {formatted_key}: {value}")

        # 如果两个阶段都完成则显示对比
        if hasattr(self, 'learning_metrics') and hasattr(self, 'replay_metrics'):
            if self.learning_metrics['success'] and self.replay_metrics['replay_used']:
                print("\n  📈 性能对比：")
                print(f"     阶段 1（学习）：")
                print(f"        - 时间：{self.learning_metrics['time']:.2f}秒")
                print(f"        - LLM 调用：{self.learning_metrics['llm_calls']}")
                print(f"     阶段 2（回放）：")
                print(f"        - 时间：{self.replay_metrics['time']:.2f}秒")
                print(f"        - LLM 调用：0")

                improvement = (1 - self.replay_metrics['time'] / self.learning_metrics['time']) * 100
                print(f"\n     🚀 整体改进：回放加速 {improvement:.0f}%！")

        print("\n" + "=" * 70)
        print("演示成功完成")
        print("=" * 70)
    
    def save_results(self):
        """将学习/回放指标和知识库统计持久化到 JSON 文件。"""
        from learning_agent import KnowledgeBase

        kb = KnowledgeBase(self.knowledge_base_path)
        payload = {
            'model': self.llm_model,
            'knowledge_base_path': self.knowledge_base_path,
            'headless': self.headless,
            'max_steps': self.max_steps,
            'learning_task': self.learning_task.strip(),
            'replay_task': self.replay_task.strip(),
            'learning_metrics': getattr(self, 'learning_metrics', None),
            'replay_metrics': getattr(self, 'replay_metrics', None),
            'knowledge_base_stats': kb.get_statistics(),
        }

        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print(f"\n💾 结果已保存到：{self.output_path}")

    def _get_llm(self):
        """根据配置获取 LLM 实例（使用项目根目录 .env 配置）。"""
        return make_llm(self.llm_model)


async def quick_test(model=DEFAULT_MODEL, headless=False, max_steps=15,
                     knowledge_base_path="./test_knowledge", task=None):
    """使用单个简单任务进行快速测试（无回放对比）。"""
    print("\n🧪 快速测试 - 简单邮件任务")
    print("-" * 40)

    task = task or "前往 ethereal.email 并向 demo@test.com 发送测试邮件"

    llm = make_llm(model)
    agent = LearningAgent(
        task=task,
        llm=llm,
        knowledge_base_path=knowledge_base_path,
        headless=headless
    )

    print(f"任务：{task}")
    result = await agent.run(max_steps=max_steps)

    print(f"\n结果：{'成功' if result['success'] else '失败'}")
    print(f"耗时：{result['execution_time']:.2f}秒")
    print(f"LLM 调用：{result.get('llm_calls', 0)}")


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器（RPA 邮件学习/回放演示）。"""
    parser = argparse.ArgumentParser(
        prog="demo_email.py",
        description=(
            "browser-use RPA 演示：学习一次「发送邮件」工作流，之后用不同参数高速回放。\n"
            "第一阶段（学习）通过多模态大模型逐步探索并录制工作流；\n"
            "第二阶段（回放）直接复用工作流、无需再调用大模型，对比耗时与调用次数。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python demo_email.py                       # 运行完整的「学习→回放」对比演示\n"
            "  python demo_email.py --quick               # 只跑一次简单任务，快速冒烟测试\n"
            "  python demo_email.py --model gemini-2.0-flash-exp --headless\n"
            "  python demo_email.py --task '给 a@b.com 发主题为\"报告\"的邮件' \\\n"
            "                       --replay-task '给 c@d.com 发主题为\"周报\"的邮件' \\\n"
            "                       --output results.json\n"
        ),
    )
    parser.add_argument(
        "--task", default=None,
        help="学习阶段的任务描述（默认：向 test@example.com 发送测试邮件）",
    )
    parser.add_argument(
        "--replay-task", default=None,
        help="回放阶段的任务描述，参数不同但流程相同（默认：向 another@example.com 发送邮件）",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help="使用的大模型，gpt-* 走 OpenAI（缺 Key 时走 OpenRouter 兜底），"
             "gemini-* 走 Google（默认：gpt-5.6-luna）",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="以无界面（headless）模式运行浏览器（默认：显示浏览器窗口）",
    )
    parser.add_argument(
        "--knowledge-base", default="./email_knowledge", metavar="PATH",
        help="工作流知识库的存储目录（默认：./email_knowledge）",
    )
    parser.add_argument(
        "--max-steps", type=int, default=20, metavar="N",
        help="学习阶段允许的最大操作步数（默认：20）",
    )
    parser.add_argument(
        "--output", default=None, metavar="PATH",
        help="将学习/回放的指标对比与知识库统计写入指定 JSON 文件",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="快速冒烟测试：只运行一次简单任务，不做学习/回放对比",
    )
    return parser


def main():
    """Main entry point."""
    args = build_parser().parse_args()

    if args.quick:
        # Run quick test (single task, no replay comparison)
        asyncio.run(quick_test(
            model=args.model,
            headless=args.headless,
            max_steps=args.max_steps,
            knowledge_base_path=args.knowledge_base,
            task=args.task,
        ))
    else:
        # Run full learning + replay demo
        demo = EmailDemo(
            llm_model=args.model,
            knowledge_base_path=args.knowledge_base,
            headless=args.headless,
            max_steps=args.max_steps,
            learning_task=args.task,
            replay_task=args.replay_task,
            output_path=args.output,
        )
        asyncio.run(demo.run_full_demo())


if __name__ == "__main__":
    main()
