"""
演示事件驱动 Agent 与 MCP 工具的集成
"""

import os
import sys
import asyncio
from datetime import datetime

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from agent import EventTriggeredAgent, SystemHintConfig
from event_types import Event, EventType
from llm.client import get_llm_client


async def main():
    """
    主示例函数
    """
    print("=" * 80)
    print("事件驱动 Agent 与 MCP 工具示例")
    print("=" * 80)
    print()

    # 检查 LLM 客户端
    try:
        client = get_llm_client()
        print(f"✅ LLM 客户端初始化成功（提供商: {client.provider}，模型: {client.model_name}）")
    except Exception as e:
        print(f"❌ 错误: 无法初始化 LLM 客户端 - {e}")
        print("   请确保项目根目录的 .env 文件中配置了正确的 API 密钥")
        return

    # 创建 Agent 配置
    config = SystemHintConfig(
        enable_timestamps=True,
        enable_tool_counter=True,
        enable_todo_list=True,
        enable_detailed_errors=True,
        enable_system_state=True,
        save_trajectory=True,
        trajectory_file="example_trajectory.json",
        use_mcp_servers=True  # 启用 MCP 服务器
    )

    # 初始化 Agent
    print("正在初始化 Agent...")
    agent = EventTriggeredAgent(
        api_key=None,  # 使用统一客户端
        provider=client.provider,
        model=client.model_name,
        config=config,
        verbose=True
    )

    # 加载 MCP 工具
    print("\n正在加载 MCP 工具...")
    await agent.load_mcp_tools()

    print("\n" + "=" * 80)
    print("测试事件处理")
    print("=" * 80)
    print()

    # 创建测试事件
    event = Event(
        event_type=EventType.WEB_MESSAGE,
        content="搜索网络上的 'Python 异步编程最佳实践' 并总结前 3 条结果。",
        metadata={
            "source": "web_interface",
            "user_id": "demo_user",
            "session_id": "test_session_001"
        }
    )

    # 处理事件
    try:
        result = agent.handle_event(event, max_iterations=15)

        print("\n" + "=" * 80)
        print("结果摘要")
        print("=" * 80)
        print(f"成功: {result['success']}")
        print(f"迭代次数: {result['iterations']}")
        print(f"工具调用: {len(result['tool_calls'])}")

        if result.get('final_answer'):
            print(f"\n最终答案:\n{result['final_answer']}")

        if result.get('trajectory_file'):
            print(f"\n轨迹已保存到: {result['trajectory_file']}")

    except Exception as e:
        print(f"\n❌ 处理事件时出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理 MCP 连接
        print("\n正在清理 MCP 连接...")
        await agent.mcp_manager.disconnect_all()
        print("✅ 清理完成")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
