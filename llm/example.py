"""
LLM 通用封装使用示例
====================

演示如何在各个章节中使用统一的 LLM 配置。
"""

from llm.client import get_llm_client, print_config, get_llm_config


# ============================================
# 示例 1: 基础使用（推荐）
# ============================================

def example_basic():
    """基础使用示例：自动从 .env 读取配置"""
    print("\n=== 示例 1: 基础使用 ===\n")

    # 获取客户端（自动读取 .env 配置）
    client = get_llm_client()

    # 使用客户端
    response = client.chat.completions.create(
        model=client.model_name,
        messages=[
            {"role": "user", "content": "你好，请简单介绍一下你自己"}
        ],
        temperature=0.7
    )

    print(f"模型: {client.model_name}")
    print(f"回复: {response.choices[0].message.content}")


# ============================================
# 示例 2: 查看配置
# ============================================

def example_view_config():
    """查看当前配置示例"""
    print("\n=== 示例 2: 查看配置 ===\n")

    # 打印格式化的配置信息
    print_config()

    # 或者获取配置字典
    config = get_llm_config()
    print(f"提供商: {config['provider']}")
    print(f"模型: {config['model']}")
    print(f"API: {config['base_url']}")


# ============================================
# 示例 3: 工具调用
# ============================================

def example_tool_calling():
    """工具调用示例"""
    print("\n=== 示例 3: 工具调用 ===\n")

    client = get_llm_client()

    # 定义工具
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "获取当前时间",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timezone": {
                            "type": "string",
                            "description": "时区，如 Asia/Shanghai"
                        }
                    }
                },
                "required": []
            }
        }
    ]

    response = client.chat.completions.create(
        model=client.model_name,
        messages=[
            {"role": "user", "content": "现在北京时间几点了？"}
        ],
        tools=tools
    )

    print(f"回复: {response.choices[0].message.content}")


# ============================================
# 示例 4: Agent 集成
# ============================================

class SimpleAgent:
    """简单的 Agent 示例，展示如何集成 LLM 客户端"""

    def __init__(self):
        """初始化 Agent，使用统一的 LLM 配置"""
        self.client = get_llm_client()
        self.conversation_history = []

    def chat(self, user_message: str) -> str:
        """
        与 Agent 对话

        Args:
            user_message: 用户消息

        Returns:
            Agent 回复
        """
        # 添加用户消息
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # 调用 LLM
        response = self.client.chat.completions.create(
            model=self.client.model_name,
            messages=self.conversation_history
        )

        assistant_message = response.choices[0].message.content

        # 添加助手消息
        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })

        return assistant_message


def example_agent():
    """Agent 集成示例"""
    print("\n=== 示例 4: Agent 集成 ===\n")

    agent = SimpleAgent()

    response1 = agent.chat("你好，我是小明")
    print(f"用户: 你好，我是小明")
    print(f"Agent: {response1}")

    response2 = agent.chat("我刚才叫什么名字？")
    print(f"用户: 我刚才叫什么名字？")
    print(f"Agent: {response2}")


# ============================================
# 示例 5: 在章节中使用
# ============================================

def chapter_example():
    """
    章节代码示例

    在各章节的代码中，只需导入并使用 get_llm_client()：
    """
    # chapterN/my_module.py

    from llm.client import get_llm_client

    # 获取客户端（自动读取 .env）
    client = get_llm_client()

    # 使用客户端
    # ... 你的代码 ...

    print("""
在各章节中使用时，只需：

1. 导入: from llm.client import get_llm_client
2. 获取客户端: client = get_llm_client()
3. 使用: client.chat.completions.create(...)

无需重复实现 LLM 客户端，无需创建独立的 .env 文件。
    """)


# ============================================
# 主函数
# ============================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  LLM 通用封装使用示例")
    print("="*60)

    # 运行示例
    # example_basic()
    # example_view_config()
    # example_tool_calling()
    # example_agent()
    chapter_example()

    print("\n提示：取消注释函数调用来运行不同示例\n")
