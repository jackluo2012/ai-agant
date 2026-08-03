"""
对话代理 - 专注于对话而不直接管理记忆
记忆更新由单独的后台进程处理
"""

import json
import logging
import sys
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import uuid

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from llm.client import get_llm_client
except ImportError:
    get_llm_client = None

from config import Config, MemoryMode
from conversation_history import ConversationHistory, ConversationTurn
from memory_manager import create_memory_manager, BaseMemoryManager, MemoryMode


def _reasoning_safe_temperature(model, requested=1.0):
    """推理模型（Kimi K3, GPT-5, ...）只接受 temperature=1。
    对于这些模型返回 1；其他提供商（豆包、DeepSeek、旧版 Moonshot）保持不变。"""
    m = str(model or "").lower().replace("/", "-")
    return 1 if ("kimi-k3" in m or "gpt-5" in m) else requested

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class ConversationConfig:
    """对话代理配置"""
    enable_memory_context: bool = True  # 在上下文中包含记忆但不更新
    enable_conversation_history: bool = True
    max_memory_context: int = 10
    temperature: float = 0.7
    max_tokens: int = 4096


class ConversationalAgent:
    """
    纯对话代理，专注于对话
    从记忆中读取上下文但不直接更新
    """

    def __init__(self,
                 user_id: str,
                 provider: Optional[str] = None,
                 model: Optional[str] = None,
                 config: Optional[ConversationConfig] = None,
                 memory_mode: MemoryMode = MemoryMode.NOTES,
                 verbose: bool = True):
        """
        初始化对话代理

        Args:
            user_id: 唯一用户标识符
            provider: LLM 提供商（通过环境变量 LLM_PROVIDER 配置）
            model: 模型名称（通过环境变量 LLM_MODEL 配置）
            config: 代理配置
            memory_mode: 记忆存储模式
            verbose: 启用详细日志
        """
        self.user_id = user_id
        self.verbose = verbose
        self.config = config or ConversationConfig()
        self.memory_mode = memory_mode

        # 使用统一的 LLM 客户端
        self.client = get_llm_client(
            provider=provider,
            model=model
        )
        self.provider = self.client.provider
        self.model = self.client.model_name

        # 初始化记忆管理器（只读访问）
        self.memory_manager = create_memory_manager(user_id, memory_mode)

        # 初始化对话历史
        self.conversation_history = ConversationHistory(user_id) if self.config.enable_conversation_history else None

        # 跟踪当前会话
        self.session_id = self._generate_session_id()
        self.conversation = []

        # 初始化系统提示词
        self._init_system_prompt()

        logger.info(f"对话代理已为用户 {user_id} 初始化，使用 {self.provider} 提供商的 {self.model} 模型")

    def _generate_session_id(self) -> str:
        """生成唯一的会话 ID"""
        return f"session-{uuid.uuid4().hex[:8]}"

    def _init_system_prompt(self):
        """初始化系统提示词"""
        system_content = """你是一个有用且个性化的助手。你可以访问来自先前对话的用户信息，这有助于你提供个性化和符合上下文的响应。

你必须详细分析上下文、用户的问题和记忆，并提供全面且详细的响应。
"""

        self.conversation = [
            {
                "role": "system",
                "content": system_content
            }
        ]
    
    def _get_memory_context(self) -> str:
        """获取当前记忆上下文字符串"""
        if not self.config.enable_memory_context:
            return ""

        context_parts = []

        # 后台处理器通过自己的管理器实例写入记忆；从磁盘重新加载，
        # 使其更新在会话中可见（与 main.py 在处理后重新加载的原因相同）。
        self.memory_manager.load_memory()

        # 添加记忆摘要
        memory_str = self.memory_manager.get_context_string()
        if memory_str:
            context_parts.append("=== 用户上下文 ===")
            context_parts.append(memory_str)
            context_parts.append("")

        # 添加所有对话历史
        if self.conversation_history:
            # 获取所有对话历史，不仅仅是最近的
            all_conversations = self.conversation_history.conversations if hasattr(self.conversation_history, 'conversations') else []

            if all_conversations:
                context_parts.append("=== 完整对话历史 ===")
                context_parts.append(f"总对话数: {len(all_conversations)}")
                context_parts.append("")

                for turn in all_conversations:
                    context_parts.append(f"[会话: {turn.session_id}, 轮次 {turn.turn_number}, 时间: {turn.timestamp}]")
                    context_parts.append(f"用户: {turn.user_message}")
                    context_parts.append(f"助手: {turn.assistant_message}")
                    context_parts.append("")

        return "\n".join(context_parts)

    def get_conversation_context(self) -> List[Dict[str, str]]:
        """
        获取完整的对话上下文用于后台记忆处理

        Returns:
            对话消息列表
        """
        # 返回对话的副本，不包含系统提示词
        return [msg for msg in self.conversation[1:] if msg.get('role') != 'system']
    
    def chat(self, message: str) -> str:
        """
        与用户进行对话

        Args:
            message: 用户消息

        Returns:
            助手响应
        """
        # Add memory context to the user message
        memory_context = self._get_memory_context()
        
        if memory_context:
            full_message = f"{message}\n\n{memory_context}"
        else:
            full_message = message
        
        # 记录完整提示词（如果启用详细日志）
        if self.verbose:
            logger.info(f"用户请求: {message}")
            if memory_context:
                logger.info(f"已添加记忆上下文: {memory_context}")
            logger.info(f"发送到 API 的完整提示词: {full_message}")

        # 仅持久化原始消息；记忆/历史上下文块作为此调用的最后一条消息临时发送。
        # 持久化 full_message 会在每个用户轮次中嵌入整个历史记录，
        # 而对话本身已经包含了之前的轮次，因此每个轮次的 token 数会按 O(N²) 增长。
        self.conversation.append({"role": "user", "content": message})
        api_messages = self.conversation[:-1] + [{"role": "user", "content": full_message}]

        try:
            # 使用流式调用模型
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                temperature=_reasoning_safe_temperature(self.model, self.config.temperature),
                max_tokens=self.config.max_tokens,
                stream=True
            )

            # 收集流式响应
            assistant_message = ""
            if self.verbose:
                logger.info("正在流式输出响应...")

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    assistant_message += delta
                    # 始终流式输出以显示实时响应
                    print(delta, end='', flush=True)

            print()  # 流式输出后换行

            # 将助手响应添加到对话
            self.conversation.append({
                "role": "assistant",
                "content": assistant_message
            })

            # 保存到对话历史
            if self.conversation_history:
                self.conversation_history.add_turn(
                    session_id=self.session_id,
                    user_message=message,
                    assistant_message=assistant_message
                )

            if self.verbose:
                logger.info(f"用户: {message}")
                logger.info(f"助手: {assistant_message}")

            return assistant_message

        except Exception as e:
            error_msg = f"对话期间出错: {str(e)}"
            logger.error(error_msg)
            return f"抱歉，我遇到了一个错误: {str(e)}"

    def reset_session(self):
        """开始新的对话会话"""
        self.session_id = self._generate_session_id()
        self._init_system_prompt()
        logger.info(f"已开始新会话: {self.session_id}")

    def get_session_id(self) -> str:
        """获取当前会话 ID"""
        return self.session_id
