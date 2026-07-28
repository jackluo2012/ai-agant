"""
LLM Tool Calling Implementation for llama.cpp
使用 llama.cpp 的 OpenAI 兼容 API
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Generator
from tools import ToolRegistry
from config import LLAMA_HOST, LLAMA_PORT, LLAMA_MODEL, LLAMA_OPENAI_COMPATIBLE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMOpenAICompatibleAgent:
    """使用 llama.cpp 的 OpenAI 兼容 API"""

    def __init__(self, model: str = None, host: str = None, port: int = None):
        """
        初始化 Agent

        Args:
            model: 模型名称 (默认: MiniCPM5-1B-Q4_K_M.gguf)
            host: llama.cpp 服务器地址 (默认: 从配置读取)
            port: llama.cpp 服务器端口 (默认: 11434)
        """
        self.model = model or LLAMA_MODEL
        self.host = host or LLAMA_HOST
        self.port = port if port is not None else LLAMA_PORT

        # 构建 base URL
        if self.host != 'localhost' and self.host != '127.0.0.1':
            self.base_url = f"http://{self.host}:{self.port}/v1"
        else:
            self.base_url = LLAMA_OPENAI_COMPATIBLE_URL

        from openai import OpenAI
        self.client = OpenAI(
            base_url=self.base_url,
            api_key="llama-cpp"  # llama.cpp 不需要真实的 key
        )

        self.tool_registry = ToolRegistry()
        self.conversation_history = []

        logger.info(f"🌐 连接到 llama.cpp 服务器: {self.base_url}")
        logger.info(f"📦 使用模型: {self.model}")

    def chat(self, message: str, use_tools: bool = True,
             temperature: float = 0.3) -> str:
        """
        发送消息并获取回复（非流式）

        Args:
            message: 用户消息
            use_tools: 是否启用工具调用
            temperature: 采样温度

        Returns:
            模型的最终回复
        """
        # 添加用户消息
        self.conversation_history.append({
            "role": "user",
            "content": message
        })

        # 准备工具
        tools = self.tool_registry.get_tool_schemas() if use_tools else None

        try:
            # 调用 API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation_history,
                tools=tools,
                tool_choice="auto" if tools else None,
                temperature=temperature
            )

            assistant_message = response.choices[0].message

            # 检查是否有工具调用
            if assistant_message.tool_calls:
                logger.info(f"🔧 模型请求了 {len(assistant_message.tool_calls)} 个工具")

                # 添加助手消息到历史
                self.conversation_history.append({
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in assistant_message.tool_calls
                    ]
                })

                # 执行工具调用（并行执行）
                def run_one(tool_call):
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    return self.tool_registry.execute_tool(
                        tool_call.function.name,
                        args
                    )

                tool_calls_list = list(assistant_message.tool_calls)
                if len(tool_calls_list) <= 1:
                    results = [run_one(tc) for tc in tool_calls_list]
                else:
                    with ThreadPoolExecutor(max_workers=len(tool_calls_list)) as executor:
                        results = list(executor.map(run_one, tool_calls_list))

                # 添加工具结果到历史
                for tool_call, result in zip(tool_calls_list, results):
                    self.conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })

                # 获取最终回复
                final_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.conversation_history,
                    tools=tools,
                    temperature=temperature
                )

                final_content = final_response.choices[0].message.content

                # 添加到历史
                self.conversation_history.append({
                    "role": "assistant",
                    "content": final_content
                })

                return final_content

            else:
                # 没有工具调用，直接返回回复
                content = assistant_message.content
                self.conversation_history.append({
                    "role": "assistant",
                    "content": content
                })
                return content

        except Exception as e:
            logger.error(f"❌ 错误: {e}")
            return f"错误: {e}"

    def chat_stream(self, message: str, use_tools: bool = True,
                    temperature: float = 0.3) -> Generator[Dict, None, None]:
        """
        流式发送消息并处理工具调用

        Yields:
            包含 type 和 content 的字典:
            - type: 'content', 'tool_call', 'tool_result', 'error'
            - content: 实际内容
        """
        # 添加用户消息
        self.conversation_history.append({
            "role": "user",
            "content": message
        })

        # 准备工具
        tools = self.tool_registry.get_tool_schemas() if use_tools else None

        # ReAct 循环 - 持续直到不需要更多工具调用
        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            try:
                # 获取流式响应
                stream_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.conversation_history,
                    tools=tools,
                    stream=True,
                    temperature=temperature
                )

                collected_content = []
                pending_tool_calls = []
                tool_calls_detected = False

                # 处理流
                for chunk in stream_response:
                    delta = chunk.choices[0].delta

                    # 处理内容
                    if delta.content:
                        content_chunk = delta.content
                        collected_content.append(content_chunk)
                        yield {"type": "content", "content": content_chunk}

                    # 处理工具调用
                    if delta.tool_calls:
                        tool_calls_detected = True
                        for tool_call_delta in delta.tool_calls:
                            if tool_call_delta.function:
                                tool_name = tool_call_delta.function.name or ""
                                tool_args = tool_call_delta.function.arguments or ""

                                # 累积工具调用参数
                                existing = next(
                                    (tc for tc in pending_tool_calls
                                     if tc.get('temp_id') == chunk.id),
                                    None
                                )
                                if existing:
                                    existing['function']['arguments'] += tool_args
                                else:
                                    pending_tool_calls.append({
                                        'temp_id': chunk.id,
                                        'function': {
                                            'name': tool_name,
                                            'arguments': tool_args
                                        }
                                    })
                                    yield {"type": "tool_call", "content": {
                                        "name": tool_name,
                                        "arguments": tool_args
                                    }}

                # 执行工具调用
                if pending_tool_calls:
                    def run_one(tool_call):
                        try:
                            args = json.loads(tool_call['function']['arguments'])
                        except json.JSONDecodeError:
                            args = {}
                        return self.tool_registry.execute_tool(
                            tool_call['function']['name'],
                            args
                        )

                    results = [run_one(tc) for tc in pending_tool_calls]

                    for result in results:
                        yield {"type": "tool_result", "content": result}
                        self.conversation_history.append({
                            "role": "tool",
                            "content": result
                        })

                # 保存完整回复
                complete_response = ''.join(collected_content)

                if tool_calls_detected:
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": complete_response if complete_response else ""
                    })
                else:
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": complete_response
                    })
                    break  # 退出 ReAct 循环

            except Exception as e:
                logger.error(f"❌ 流式聊天错误: {e}")
                yield {"type": "error", "content": str(e)}
                break

        if iteration >= max_iterations:
            yield {"type": "error", "content": "达到最大迭代次数"}

    def reset_conversation(self):
        """重置对话历史"""
        self.conversation_history = []
        logger.info("对话历史已重置")


def test_connection():
    """测试与 llama.cpp 服务器的连接"""
    print("="*60)
    print("🧪 测试 llama.cpp 连接")
    print("="*60)

    print(f"\n📋 当前配置:")
    print(f"   服务器: http://{LLAMA_HOST}:{LLAMA_PORT}")
    print(f"   模型: {LLAMA_MODEL}")

    try:
        agent = LLMOpenAICompatibleAgent()

        # 测试简单对话
        print("\n📝 测试简单对话...")
        response = agent.chat("你好，请用一句话介绍你自己。")
        print(f"🤖 回复: {response}")

        # 测试工具调用
        print("\n🔧 测试工具调用...")
        response = agent.chat("15 * 23 等于多少？", use_tools=True)
        print(f"🤖 回复: {response}")

        print("\n✅ 所有测试通过!")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        print(f"   请确认 llama.cpp 正在运行于 http://{LLAMA_HOST}:{LLAMA_PORT}")


def demo():
    """交互式演示"""
    print("="*60)
    print("🎯 llama.cpp Tool Calling 演示")
    print("="*60)

    print(f"\n📋 当前配置:")
    print(f"   服务器: http://{LLAMA_HOST}:{LLAMA_PORT}")
    print(f"   模型: {LLAMA_MODEL}")

    try:
        agent = LLMOpenAICompatibleAgent()
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        return

    print("\n💬 与助手对话 (输入 'exit' 退出)")
    print("-"*40)

    while True:
        user_input = input("\n👤 你: ").strip()
        if user_input.lower() in ['exit', 'quit', '退出']:
            break

        response = agent.chat(user_input)
        print(f"🤖 助手: {response}")

    print("\n👋 再见!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_connection()
    else:
        demo()
