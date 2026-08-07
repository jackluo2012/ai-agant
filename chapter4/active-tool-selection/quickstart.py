"""
主动工具选择快速入门

运行此脚本以查看主动工具发现的基本演示。
"""

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

from agent import ActiveToolAgent, PassiveToolAgent
from tool_knowledge_base import create_tool_knowledge_base, calculate_total_tokens


def main():
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║                    主动工具选择 - 快速入门                                  ║
║                    受 MCP-Zero 启发 (arXiv:2506.01056)                       ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝

本演示展示主动工具发现如何使代理能够:
  • 维持最小的上下文占用
  • 按需主动请求工具
  • 随生态系统增长高效扩展

""")

    # 显示知识库信息
    print("📚 工具知识库:")
    servers = create_tool_knowledge_base()
    total_tools = sum(len(server.tools) for server in servers)
    total_tokens = calculate_total_tokens([tool for server in servers for tool in server.tools])

    print(f"   • 服务器数量: {len(servers)}")
    print(f"   • 工具总数: {total_tools}")
    print(f"   • 全部注入的 token 成本: ~{total_tokens:,} tokens")
    print()

    # 示例任务
    task = "在 GitHub 上搜索星标超过 5000 的 Python Web 框架"
    print(f"🎯 示例任务:\n   {task}\n")

    # 使用主动代理测试
    print("=" * 80)
    print("1️⃣  主动工具发现")
    print("=" * 80)
    print("\n⏳ 代理正在分析任务并发现所需工具...\n")

    active_agent = ActiveToolAgent()
    active_result = active_agent.execute_task(task)

    print(f"✅ 使用主动发现的任务完成:\n")
    print(f"   📊 指标:")
    print(f"      • 加载的工具: {active_result['metrics']['tools_loaded']} (共 {total_tools} 个)")
    print(f"      • 使用的 tokens: {active_result['metrics']['tokens_used']:,}")
    print(f"      • 工具请求次数: {active_result['metrics']['tool_requests']}")
    print(f"      • API 调用次数: {active_result['metrics']['api_calls']}")
    print()
    print(f"   🛠️  发现的工具:")
    for tool in active_result['tools_loaded']:
        print(f"      • {tool}")
    print()

    # 使用被动代理测试
    print("=" * 80)
    print("2️⃣  被动工具注入（传统方法）")
    print("=" * 80)
    print(f"\n⏳ 代理已预加载所有 {total_tools} 个工具...\n")

    passive_agent = PassiveToolAgent()
    passive_result = passive_agent.execute_task(task)

    print(f"✅ 使用被动注入的任务完成:\n")
    print(f"   📊 指标:")
    print(f"      • 加载的工具: {passive_result['metrics']['tools_loaded']} (全部工具)")
    print(f"      • 使用的 tokens: {passive_result['metrics']['tokens_used']:,}")
    print(f"      • API 调用次数: {passive_result['metrics']['api_calls']}")
    print()

    # 对比
    print("=" * 80)
    print("3️⃣  对比")
    print("=" * 80)
    print()

    token_reduction = (1 - active_result['metrics']['tokens_used'] /
                       passive_result['metrics']['tokens_used']) * 100
    tool_reduction = (1 - active_result['metrics']['tools_loaded'] /
                      passive_result['metrics']['tools_loaded']) * 100

    print(f"📊 效率提升:\n")
    print(f"   Token 使用:")
    print(f"      • 主动: {active_result['metrics']['tokens_used']:,} tokens")
    print(f"      • 被动: {passive_result['metrics']['tokens_used']:,} tokens")
    print(f"      • 减少: {token_reduction:.1f}% 🎉")
    print()
    print(f"   加载的工具:")
    print(f"      • 主动: {active_result['metrics']['tools_loaded']} 个工具")
    print(f"      • 被动: {passive_result['metrics']['tools_loaded']} 个工具")
    print(f"      • 减少: {tool_reduction:.1f}% 🎯")
    print()

    print("=" * 80)
    print("💡 核心洞察")
    print("=" * 80)
    print("""
1. 主动发现维持代理自主性
   → 代理自主决定需要什么工具，何时需要

2. 巨大的效率提升
   → 典型任务可减少 80-98% 的 token 使用

3. 随生态系统增长而扩展
   → 增加 100 个工具不会膨胀每个请求

4. 迭代能力扩展
   → 工具链随任务理解深化而演进

5. 语义路由实现精准匹配
   → 基于语义而非关键字匹配工具

""")

    print("🎓 后续步骤:")
    print("   • 运行 'python demo_comparison.py' 查看全面对比")
    print("   • 运行 'python examples.py' 查看更多用例")
    print("   • 查看 README.md 了解架构细节")
    print()
    print("📄 参考文献: MCP-Zero 论文 - https://arxiv.org/pdf/2506.01056")
    print()


if __name__ == "__main__":
    main()
