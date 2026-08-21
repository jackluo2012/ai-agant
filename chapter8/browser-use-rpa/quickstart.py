"""
学习代理快速启动脚本

本脚本提供如何使用学习代理执行常见任务的简单示例。
"""

import asyncio
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

from dotenv import load_dotenv
from browser_use import ChatOpenAI, ChatGoogle
from learning_agent import LearningAgent
from llm_factory import make_llm

# 加载环境变量
load_dotenv()


async def example_search():
    """示例：在 Google 上搜索。"""
    print("\n🔍 示例 1：Google 搜索")
    print("-" * 40)

    agent = LearningAgent(
        task="前往 Google 并搜索 'browser automation with AI'",
        llm=make_llm(),
        knowledge_base_path="./my_knowledge",
        headless=False  # 显示浏览器
    )

    result = await agent.run(max_steps=10)
    print(f"✅ 完成，耗时 {result['execution_time']:.2f}秒")
    print(f"   LLM 调用次数：{result.get('llm_calls', 0)}")
    print(f"   工作流复用：{result.get('replay_used', False)}")


async def example_weather():
    """示例：检查天气。"""
    print("\n☀️ 示例 2：天气检查")
    print("-" * 40)

    agent = LearningAgent(
        task="查看东京的天气预报",
        llm=ChatGoogle(model="gemini-2.0-flash-exp"),  # 可以使用不同的 LLM
        knowledge_base_path="./my_knowledge",
        headless=False
    )

    result = await agent.run(max_steps=15)
    print(f"✅ 完成，耗时 {result['execution_time']:.2f}秒")

    # 再次运行不同的城市 - 应该更快！
    print("\n   正在查看纽约的天气...")
    agent2 = LearningAgent(
        task="查看纽约的天气预报",
        llm=ChatGoogle(model="gemini-2.0-flash-exp"),
        knowledge_base_path="./my_knowledge",
        headless=False
    )

    result2 = await agent2.run(max_steps=15)
    print(f"✅ 完成，耗时 {result2['execution_time']:.2f}秒")

    if result2.get('replay_used'):
        speedup = result['execution_time'] / result2['execution_time']
        print(f"   🚀 使用学习的工作流加速了 {speedup:.1f} 倍！")


async def example_custom_task():
    """示例：来自用户输入的自定义任务。"""
    print("\n💡 示例 3：自定义任务")
    print("-" * 40)

    task = input("请输入您的任务：")

    if not task:
        task = "前往 Wikipedia 并搜索 'artificial intelligence'"

    print(f"\n任务：{task}")

    agent = LearningAgent(
        task=task,
        llm=make_llm(),
        knowledge_base_path="./my_knowledge",
        headless=False
    )

    result = await agent.run(max_steps=20)

    print(f"\n✅ 任务完成！")
    print(f"   成功：{result['success']}")
    print(f"   耗时：{result['execution_time']:.2f}秒")
    print(f"   工作流复用：{result.get('replay_used', False)}")

    if not result.get('replay_used'):
        print("\n💡 提示：再次尝试相同的任务 - 会更快！")


def show_knowledge_stats():
    """显示知识库统计信息。"""
    from learning_agent import KnowledgeBase

    print("\n📊 知识库统计信息")
    print("-" * 40)

    kb = KnowledgeBase("./my_knowledge")
    stats = kb.get_statistics()

    if stats['total_workflows'] == 0:
        print("还没有学习到工作流。先运行一些任务！")
    else:
        for key, value in stats.items():
            formatted_key = key.replace('_', ' ').title()
            print(f"   {formatted_key}: {value}")

        print("\n   已学习的工作流：")
        for workflow in kb.workflows.values():
            print(f"      • {workflow.intent}")
            if workflow.success_count > 0:
                print(f"        (已使用 {workflow.success_count} 次)")


async def main():
    """主菜单。"""
    print("=" * 60)
    print("学习代理 - 快速启动")
    print("=" * 60)

    while True:
        print("\n选项：")
        print("1. Google 搜索示例")
        print("2. 天气检查示例")
        print("3. 自定义任务")
        print("4. 显示知识库统计")
        print("5. 退出")

        choice = input("\n选择选项 (1-5): ")

        if choice == "1":
            await example_search()
        elif choice == "2":
            await example_weather()
        elif choice == "3":
            await example_custom_task()
        elif choice == "4":
            show_knowledge_stats()
        elif choice == "5":
            print("\n再见！👋")
            break
        else:
            print("无效选项，请重试。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n用户中断。再见！👋")
