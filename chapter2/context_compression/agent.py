"""
上下文压缩研究 Agent
===================

支持流式输出的研究型 Agent，用于对比不同上下文压缩策略。

功能:
    - 多种压缩策略支持
    - 流式响应输出
    - 工具调用执行
    - 对话历史管理
    - Token 使用统计
    - 上下文溢出检测
"""

import json
import logging
import time
import sys
import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# 导入项目通用 LLM 客户端
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 同时添加当前目录到路径，以便本地导入
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from llm.client import get_llm_client as _get_llm_client
except ImportError:
    _get_llm_client = None

# 优先使用绝对导入
try:
    from chapter2.context_compression.config import Config
    from chapter2.context_compression.web_tools import WebTools
    from chapter2.context_compression.compression_strategies import (
        CompressionStrategy,
        ContextCompressor,
        CompressedContent
    )
except ImportError:
    # 回退到本地导入
    from config import Config
    from web_tools import WebTools
    from compression_strategies import (
        CompressionStrategy,
        ContextCompressor,
        CompressedContent
    )

# 配置日志
logger = logging.getLogger(__name__)


def _is_reasoning_model(model: str) -> bool:
    """
    判断是否为推理模型

    推理模型（Kimi K3、GPT-5）只接受 temperature=1

    Args:
        model: 模型名称

    Returns:
        如果是推理模型返回 True
    """
    m = str(model or "").lower()
    return "kimi-k3" in m or "gpt-5" in m or "claude" in m


def _get_safe_temperature(model: str, requested: float = 0.3) -> float:
    """获取安全的温度参数"""
    return 1.0 if _is_reasoning_model(model) else requested


def _get_safe_max_tokens(model: str, requested: int, reasoning_budget: int = 2048) -> int:
    """获取安全的最大 token 数"""
    if _is_reasoning_model(model):
        return requested + reasoning_budget
    return requested


@dataclass
class ToolCall:
    """
    工具调用记录

    Attributes:
        tool_name: 工具名称
        arguments: 工具参数
        result: 工具执行结果
        compressed_result: 压缩后的结果
        timestamp: 调用时间戳
        id: 工具调用 ID（用于匹配响应）
    """
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    compressed_result: Optional[CompressedContent] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    # 提供商端的 tool_call id，用于将历史中的工具消息匹配回产生它的调用
    # （窗口化压缩用此恢复原始查询）
    id: Optional[str] = None


@dataclass
class AgentTrajectory:
    """
    Agent 执行轨迹

    跟踪 Agent 的完整执行过程和统计信息

    Attributes:
        tool_calls: 工具调用列表
        total_tokens_used: 总 token 使用量
        prompt_tokens_used: 累计 prompt token 数
        completion_tokens_used: 累计 completion token 数
        last_prompt_tokens: 最近一次 API 调用的 prompt token 数（当前上下文大小）
        context_overflows: 上下文溢出次数
        compression_strategy: 使用的压缩策略
        start_time: 开始时间
        end_time: 结束时间
    """
    tool_calls: List[ToolCall] = field(default_factory=list)
    total_tokens_used: int = 0
    prompt_tokens_used: int = 0
    completion_tokens_used: int = 0
    # 最近一次 API 调用的 prompt tokens = 当前上下文大小
    # 上面的 prompt_tokens_used 是累计成本计数器（每次调用重新计算共享前缀），
    # 因此不能与每请求上下文窗口进行比较
    last_prompt_tokens: int = 0
    context_overflows: int = 0
    compression_strategy: CompressionStrategy = CompressionStrategy.NO_COMPRESSION
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None


class ResearchAgent:
    """
    研究型 Agent

    带上下文压缩的研究助手

    Attributes:
        client: LLM 客户端
        model: 模型名称
        compression_strategy: 压缩策略
        verbose: 详细日志
        enable_streaming: 流式输出
        web_tools: 网页工具实例
        compressor: 压缩器实例
        trajectory: 执行轨迹
        conversation_history: 对话历史
    """

    def __init__(
        self,
        compression_strategy: CompressionStrategy = CompressionStrategy.NO_COMPRESSION,
        verbose: bool = False,
        enable_streaming: bool = True
    ):
        """
        初始化研究 Agent

        Args:
            compression_strategy: 上下文压缩策略
            verbose: 启用详细日志
            enable_streaming: 启用流式响应
        """
        # 使用统一的 LLM 客户端
        if _get_llm_client is None:
            raise ImportError(
                "无法导入 LLM 客户端。请确保：\n"
                "1. 项目根目录的 llm/client.py 存在\n"
                "2. 已安装必要的依赖（openai, python-dotenv）\n"
                "3. 根目录的 .env 文件已正确配置"
            )
        self.client = _get_llm_client()
        self.model = self.client.model_name
        self.compression_strategy = compression_strategy
        self.verbose = verbose
        self.enable_streaming = enable_streaming

        # 初始化工具
        self.web_tools = WebTools()
        self.compressor = ContextCompressor(compression_strategy, enable_streaming)

        # 初始化轨迹
        self.trajectory = AgentTrajectory(compression_strategy=compression_strategy)

        # 初始化对话历史
        self.conversation_history = []
        self._init_system_prompt()

        logger.info(f"研究 Agent 初始化完成 - 压缩策略: {compression_strategy.value}")

    def _init_system_prompt(self):
        """初始化 OpenAI 联合创始人研究的系统提示"""
        from datetime import datetime
        today = datetime.now()
        date_string = today.strftime("%Y年%m月%d日 %A")

        self.conversation_history = [
            {
                "role": "system",
                "content": f"""你是一个负责查找 OpenAI 联合创始人信息的研究助手。

你的任务是：
1. 首先，搜索并识别所有 OpenAI 联合创始人
2. 然后，逐个搜索每位联合创始人的当前归属
3. 汇总一份包含每位联合创始人当前状态的完整报告

重要指示：
- 要全面和系统化 - 逐个搜索每个人
- 重点关注当前归属，而非历史职位
- 包含公司名称、职位和任何近期变动
- 如果有人离开某个职位，注明他们去了哪里
- 收集完所有信息后，提供最终答案，包含完整列表

可用工具：
- search_web: 搜索网络信息
- fetch_webpage: 获取特定网页内容

请从搜索 OpenAI 联合创始人完整列表开始。

今天的日期：{date_string}"""
            }
        ]

    def _get_tools_description(self) -> List[Dict[str, Any]]:
        """
        获取工具描述

        Returns:
            工具描述列表
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "搜索网络信息。返回多个搜索结果，每个结果包含网页内容。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索查询"
                            },
                            "num_results": {
                                "type": "integer",
                                "description": "返回结果数量（默认：5）",
                                "default": 5
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_webpage",
                    "description": "获取特定网页 URL 并提取文本内容",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "网页 URL"
                            }
                        },
                        "required": ["url"]
                    }
                }
            }
        ]

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[Any, Optional[CompressedContent]]:
        """
        执行工具并返回结果（可选压缩）

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            (工具结果, 压缩内容（如适用）) 元组
        """
        if tool_name == "search_web":
            result = self.web_tools.search_web(**arguments)

            # 应用压缩策略
            query = arguments.get('query', '')
            current_context = self._get_current_context_summary()
            compressed = self.compressor.compress_search_results(
                result,
                query,
                current_context
            )

            return result, compressed

        elif tool_name == "fetch_webpage":
            result = self.web_tools.fetch_webpage(**arguments)

            # 对于 fetch，通常不压缩（用于追问）
            return result, None

        else:
            return {"error": f"未知工具: {tool_name}"}, None

    def _get_current_context_summary(self) -> str:
        """
        获取当前上下文摘要（用于上下文感知压缩）

        Returns:
            上下文摘要字符串
        """
        if not self.trajectory.tool_calls:
            return ""

        # 获取最近几次工具调用的上下文
        recent_calls = self.trajectory.tool_calls[-3:]
        context_parts = []

        for call in recent_calls:
            context_parts.append(f"上次搜索: {call.arguments.get('query', 'N/A')}")

        return " | ".join(context_parts)

    def _handle_windowed_compression(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        应用窗口化压缩策略到消息历史

        只在上下文使用超过 80% 阈值时压缩

        Args:
            messages: 当前消息历史

        Returns:
            需要时压缩历史后的消息
        """
        if self.compression_strategy != CompressionStrategy.WINDOWED_CONTEXT:
            return messages

        # 检查是否应该开始压缩（80% 上下文使用）
        # 使用最近一次调用的 prompt 大小（当前上下文），而不是累计成本计数器
        context_threshold = Config.CONTEXT_WINDOW_SIZE * 0.8

        if self.trajectory.last_prompt_tokens <= context_threshold:
            logger.debug(f"窗口化压缩: 上下文使用低于阈值 ({self.trajectory.last_prompt_tokens:,}/{context_threshold:.0f} tokens)")
            return messages  # 暂不需要压缩

        logger.info(f"⚠️ 上下文使用超过 80% 阈值 ({self.trajectory.last_prompt_tokens:,}/{Config.CONTEXT_WINDOW_SIZE} tokens) - 开始压缩")

        # 压缩标记，用于识别已压缩消息
        COMPRESSION_MARKER = "[已压缩]"

        # 统计需要压缩的工具消息
        tool_messages_to_compress = []
        already_compressed_count = 0

        for i, msg in enumerate(messages):
            if msg.get('role') == 'tool':
                original_content = msg.get('content', '')
                if original_content.startswith(COMPRESSION_MARKER):
                    already_compressed_count += 1
                else:
                    tool_messages_to_compress.append((i, msg))

        total_tool_messages = already_compressed_count + len(tool_messages_to_compress)

        if not tool_messages_to_compress:
            logger.debug(f"窗口化压缩: 所有 {total_tool_messages} 个工具消息已压缩")
            return messages  # 所有工具消息已压缩

        logger.info(f"📊 正在压缩 {len(tool_messages_to_compress)} 个未压缩工具消息（总共 {total_tool_messages} 个）")

        # 构建压缩结果
        compressed_messages = []
        compressed_in_this_pass = 0

        for i, msg in enumerate(messages):
            if msg.get('role') == 'tool':
                original_content = msg.get('content', '')

                # 检查是否已压缩
                if original_content.startswith(COMPRESSION_MARKER):
                    # 已压缩，保持不变
                    compressed_messages.append(msg)
                else:
                    # 压缩此工具结果
                    compressed_in_this_pass += 1

                    # 查找对应的工具调用以获取上下文
                    tool_call_id = msg.get('tool_call_id')
                    query = "信息搜索"  # 默认

                    # 尝试从工具调用中查找查询
                    for call in self.trajectory.tool_calls:
                        if call.id is not None and call.id == tool_call_id:
                            query = call.arguments.get('query', query)
                            break

                    logger.debug(f"正在压缩工具消息 {compressed_in_this_pass}/{len(tool_messages_to_compress)}，索引 {i}（查询: {query[:50]}...）")
                    compressed = self.compressor.compress_for_history(
                        original_content,
                        'search_web',
                        query,
                        preserve_citations=True
                    )
                    logger.debug(f"已压缩: {compressed.original_length:,} → {compressed.compressed_length:,} 字符")

                    # 标记为压缩
                    compressed_content = (
                        f"{COMPRESSION_MARKER} "
                        f"[原始: {compressed.original_length:,} 字符 → 压缩: {compressed.compressed_length:,} 字符]\n"
                        f"{compressed.content}"
                    )

                    compressed_messages.append({
                        **msg,
                        'content': compressed_content
                    })
            else:
                compressed_messages.append(msg)

        logger.info(f"✅ 本次通过压缩了 {compressed_in_this_pass} 个工具消息")

        return compressed_messages

    def _stream_response(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        流式获取模型响应

        Args:
            messages: 对话消息

        Returns:
            包含 token 使用情况的完整消息对象
        """
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self._get_tools_description(),
                tool_choice="auto",
                temperature=_get_safe_temperature(self.model, Config.MODEL_TEMPERATURE),
                max_tokens=Config.MODEL_MAX_TOKENS,
                stream=True,
                stream_options={"include_usage": True}  # 请求流中的 token 使用情况
            )

            collected_chunks = []
            collected_messages = []
            current_tool_calls = []
            usage_data = None

            print("\n🤖 助手: ", end="", flush=True)

            for chunk in stream:
                collected_chunks.append(chunk)

                # 捕获使用情况数据（可能在没有 choices 的块中）
                if hasattr(chunk, 'usage') and chunk.usage is not None:
                    usage_data = chunk.usage

                # 在访问前检查块是否有 choices
                if hasattr(chunk, 'choices') and chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta

                    # 处理内容
                    if hasattr(delta, 'content') and delta.content:
                        content = delta.content
                        print(content, end="", flush=True)
                        collected_messages.append(content)

                    # 处理流中的工具调用
                    if hasattr(delta, 'tool_calls') and delta.tool_calls:
                        for tool_call_delta in delta.tool_calls:
                            if tool_call_delta.index is not None:
                                # 确保有足够的工具调用
                                while len(current_tool_calls) <= tool_call_delta.index:
                                    current_tool_calls.append({
                                        "id": "",
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""}
                                    })

                                if tool_call_delta.id:
                                    current_tool_calls[tool_call_delta.index]["id"] = tool_call_delta.id
                                if tool_call_delta.function:
                                    if tool_call_delta.function.name:
                                        current_tool_calls[tool_call_delta.index]["function"]["name"] = tool_call_delta.function.name
                                    if tool_call_delta.function.arguments:
                                        current_tool_calls[tool_call_delta.index]["function"]["arguments"] += tool_call_delta.function.arguments

            print("\n", flush=True)

            # 记录 token 使用情况（如果可用）
            if usage_data:
                prompt_tokens = usage_data.prompt_tokens if hasattr(usage_data, 'prompt_tokens') else 0
                completion_tokens = usage_data.completion_tokens if hasattr(usage_data, 'completion_tokens') else 0
                total_tokens = usage_data.total_tokens if hasattr(usage_data, 'total_tokens') else 0

                logger.info(f"🔢 LLM API Token 使用 - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens}")

                # 更新轨迹
                self.trajectory.last_prompt_tokens = prompt_tokens
                self.trajectory.prompt_tokens_used += prompt_tokens
                self.trajectory.completion_tokens_used += completion_tokens
                self.trajectory.total_tokens_used += total_tokens

            # 构建完整消息
            complete_message = {
                "role": "assistant",
                "content": "".join(collected_messages) if collected_messages else None
            }

            if current_tool_calls:
                complete_message["tool_calls"] = current_tool_calls

            return complete_message

        except Exception as e:
            logger.error(f"流式响应错误: {str(e)}")
            raise

    def _non_streaming_response(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        非流式获取模型响应

        Args:
            messages: 对话消息

        Returns:
            包含 token 使用情况的完整消息对象
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self._get_tools_description(),
            tool_choice="auto",
            temperature=_get_safe_temperature(self.model, Config.MODEL_TEMPERATURE),
            max_tokens=Config.MODEL_MAX_TOKENS,
            stream=False
        )

        message = response.choices[0].message

        # 记录 token 使用情况
        if hasattr(response, 'usage') and response.usage:
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            total_tokens = response.usage.total_tokens

            logger.info(f"🔢 LLM API Token 使用 - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens}")

            # 更新轨迹
            self.trajectory.last_prompt_tokens = prompt_tokens
            self.trajectory.prompt_tokens_used += prompt_tokens
            self.trajectory.completion_tokens_used += completion_tokens
            self.trajectory.total_tokens_used += total_tokens

        # 转换为字典格式
        message_dict = {
            "role": "assistant",
            "content": message.content
        }

        if hasattr(message, 'tool_calls') and message.tool_calls:
            message_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in message.tool_calls
            ]

        # 显示响应
        if message.content:
            print(f"\n🤖 助手: {message.content}\n")

        return message_dict

    def execute_research(self, max_iterations: int = 15) -> Dict[str, Any]:
        """
        执行研究任务

        Args:
            max_iterations: 最大工具调用次数

        Returns:
            研究结果字典
        """
        # 添加初始用户消息
        self.conversation_history.append({
            "role": "user",
            "content": "请研究并找出所有 OpenAI 联合创始人的当前归属。"
        })

        messages = self.conversation_history.copy()
        iteration = 0
        final_answer = None

        print("\n" + "="*70)
        print(f"开始研究 - 使用 {self.compression_strategy.value} 策略")
        print("="*70)

        while iteration < max_iterations:
            iteration += 1
            print(f"\n📍 迭代 {iteration}/{max_iterations}")

            try:
                # 如需，应用窗口化压缩
                if self.compression_strategy == CompressionStrategy.WINDOWED_CONTEXT:
                    messages = self._handle_windowed_compression(messages)

                # 显示当前 token 使用情况
                print(f"📊 累计 Token 使用 - Prompt: {self.trajectory.prompt_tokens_used:,}, Completion: {self.trajectory.completion_tokens_used:,}, Total: {self.trajectory.total_tokens_used:,}")

                # 检查是否接近 token 限制
                if self.trajectory.total_tokens_used > 0:  # 仅在首次调用后检查
                    # 压缩演示使用 128k 上下文预算。对比最近一次调用的 prompt 大小
                    # （实际上下文）与窗口 — 累计计数器每次调用重新计算共享前缀，
                    # 会夸大使用量呈二次方增长
                    if self.trajectory.last_prompt_tokens > Config.CONTEXT_WINDOW_SIZE * 0.8:
                        logger.warning(f"接近上下文限制: 最近一次请求有 {self.trajectory.last_prompt_tokens:,} prompt tokens")
                        self.trajectory.context_overflows += 1

                        if self.compression_strategy == CompressionStrategy.NO_COMPRESSION:
                            print("\n⚠️ 检测到上下文溢出！这展示了无压缩策略的局限性。")
                            return {
                                "error": f"上下文窗口超出 - 最近一次请求 {self.trajectory.last_prompt_tokens:,} tokens（限制: {Config.CONTEXT_WINDOW_SIZE}）",
                                "trajectory": self.trajectory,
                                "iterations": iteration
                            }

                # 获取模型响应
                if self.enable_streaming:
                    message = self._stream_response(messages)
                else:
                    message = self._non_streaming_response(messages)

                # 处理工具调用
                if message.get('tool_calls'):
                    messages.append(message)

                    if message.get('content'):
                        print(f"\n🤖 助手: {message['content']}")

                    for tool_call in message['tool_calls']:
                        function_name = tool_call['function']['name']
                        function_args = json.loads(tool_call['function']['arguments'])

                        print(f"\n🔧 正在执行: {function_name}")
                        print(f"   参数: {function_args}")

                        # 执行工具
                        result, compressed = self._execute_tool(function_name, function_args)

                        # 记录工具调用
                        tool_call_record = ToolCall(
                            tool_name=function_name,
                            arguments=function_args,
                            result=result,
                            compressed_result=compressed,
                            id=tool_call['id']
                        )
                        self.trajectory.tool_calls.append(tool_call_record)

                        # 确定要添加到消息的内容
                        if compressed and self.compression_strategy != CompressionStrategy.NO_COMPRESSION:
                            # 使用压缩内容
                            tool_content = compressed.content
                            print(f"   ✂️ 已压缩: {compressed.original_length:,} → {compressed.compressed_length:,} 字符")
                        else:
                            # 使用原始内容（无压缩或窗口化的最新消息）
                            if function_name == "search_web":
                                # 格式化搜索结果
                                tool_content = json.dumps(result, indent=2, ensure_ascii=False)
                            else:
                                tool_content = json.dumps(result, ensure_ascii=False)

                        # 添加工具结果到消息
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call['id'],
                            "content": tool_content
                        }
                        messages.append(tool_msg)

                        print(f"   📄 结果大小: {len(tool_content):,} 字符")

                elif message.get('content'):
                    # 无工具调用，仅有内容
                    messages.append(message)
                    final_answer = message['content']
                    logger.info("找到最终答案")
                    break

            except Exception as e:
                logger.error(f"研究过程中出错: {str(e)}")
                return {
                    "error": str(e),
                    "trajectory": self.trajectory,
                    "iterations": iteration
                }

        # 设置结束时间
        self.trajectory.end_time = time.time()

        return {
            "final_answer": final_answer,
            "trajectory": self.trajectory,
            "iterations": iteration,
            "success": final_answer is not None,
            "execution_time": self.trajectory.end_time - self.trajectory.start_time
        }

    def reset(self):
        """重置 Agent 状态"""
        self.trajectory = AgentTrajectory(compression_strategy=self.compression_strategy)
        self._init_system_prompt()
        self.web_tools.clear_cache()
        logger.info("Agent 状态已重置")
