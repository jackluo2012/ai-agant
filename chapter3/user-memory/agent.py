"""
用户记忆代理，使用 React 模式和工具调用
遵循 system-hint 项目的基于工具的方法
"""

import json
import os
import sys
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
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
from memory_manager import create_memory_manager, BaseMemoryManager
from conversation_history import ConversationHistory, ConversationTurn


def _reasoning_safe_temperature(model, requested=1.0):
    """推理模型（Kimi K3, GPT-5, ...）只接受 temperature=1。
    对于这些模型返回 1；其他提供商（豆包、DeepSeek、旧版 Moonshot）保持不变。"""
    m = str(model or "").lower().replace("/", "-")
    return 1 if ("kimi-k3" in m or "gpt-5" in m) else requested

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """表示带有跟踪的单个工具调用"""
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class UserMemoryConfig:
    """用户记忆代理配置"""
    enable_memory_updates: bool = True
    enable_conversation_history: bool = True
    enable_memory_search: bool = True
    memory_mode: MemoryMode = MemoryMode.NOTES
    max_memory_context: int = 10  # 上下文中包含的最大记忆项数
    save_trajectory: bool = True
    trajectory_file: str = "memory_trajectory.json"


class UserMemoryAgent:
    """
    使用基于工具的 React 模式的用户记忆代理
    """

    def __init__(self,
                 user_id: str,
                 provider: Optional[str] = None,
                 model: Optional[str] = None,
                 config: Optional[UserMemoryConfig] = None,
                 verbose: bool = True):
        """
        初始化代理

        Args:
            user_id: 唯一用户标识符
            provider: LLM 提供商（通过环境变量 LLM_PROVIDER 配置）
            model: 模型名称（通过环境变量 LLM_MODEL 配置）
            config: 代理配置
            verbose: 启用详细日志
        """
        self.user_id = user_id
        self.verbose = verbose
        self.config = config or UserMemoryConfig()

        # 使用统一的 LLM 客户端
        self.client = get_llm_client(
            provider=provider,
            model=model
        )
        self.provider = self.client.provider
        self.model = self.client.model_name
        
        # Initialize memory manager
        self.memory_manager = create_memory_manager(user_id, self.config.memory_mode)
        
        # Initialize conversation history
        self.conversation_history = ConversationHistory(user_id) if self.config.enable_conversation_history else None
        
        # Track tool calls
        self.tool_calls: List[ToolCall] = []
        self.tool_call_counts: Dict[str, int] = {}
        
        # Initialize conversation
        self.conversation = []
        self.session_id = self._start_session()
        
        # Initialize system prompt
        self._init_system_prompt()
        
        logger.info(f"UserMemoryAgent initialized for user {user_id} with {self.provider} provider using {self.model}")
    
    def _start_session(self) -> str:
        """Start a new session"""
        return f"session-{uuid.uuid4().hex[:8]}"
    
    def _init_system_prompt(self):
        """根据记忆模式初始化带有记忆上下文的系统提示词"""

        base_prompt = """你是一个具有跨对话持久记忆能力的智能助手。
你有权使用各种工具来管理用户记忆和搜索对话历史。如果你想要添加、更新或删除多条记忆，应该一次性调用多个工具。在完成记忆更新后，你应该只输出 STOP，不要输出任何其他文本。

最新对话的完整历史会自动加载在下方的上下文中。

## 关键行为：
1. 所有用户记忆都会自动加载并显示在下方的"用户记忆"部分
2. 当了解到关于用户的新信息时，主动更新记忆
3. 在回复时引用相关的记忆
4. 与已存储的信息保持一致性
5. 根据你对用户的了解进行个性化回复

"""
        
        # 添加特定模式的记忆说明
        if self.config.memory_mode == MemoryMode.NOTES:
            memory_instructions = """## 记忆管理：
- 所有用户记忆都已预先加载在下方的上下文中
- 使用 `add_memory` 来存储关于用户的新重要信息
- 使用 `update_memory` 来修改现有记忆
- 使用 `delete_memory` 来删除过时或不正确的记忆

将记忆保持为简单的事实或偏好。"""
        
        elif self.config.memory_mode == MemoryMode.ENHANCED_NOTES:
            memory_instructions = """## 记忆管理：
- 所有用户记忆都已预先加载在下方的上下文中
- 使用 `add_memory` 来存储关于用户的新重要信息
- 使用 `update_memory` 来修改现有记忆
- 使用 `delete_memory` 来删除过时或不正确的记忆

重要提示：每条笔记应以完整、有上下文的方式包含所有重要的事实信息和用户偏好。
笔记可以是完整的段落，能够捕捉完整的上下文，而不仅仅是简单的键值对。

增强笔记的良好示例：
- "用户在腾讯公司担任高级软件工程师，专注于机器学习领域。已工作3年，喜欢团队协作的文化氛围。"
- "用户的工作邮箱是 zhangsan@tencent.com，个人邮箱是 zhangsan.personal@gmail.com。工作时间内只使用工作邮箱。"
- "用户有两个孩子：张小明（8岁，热爱足球）和张小红（5岁，对恐龙感兴趣）。两人都就读于育才小学。"

从对话中提取所有可能对未来互动有用的事实信息。"""

        elif self.config.memory_mode == MemoryMode.JSON_CARDS:
            memory_instructions = """## 记忆管理：
- 所有用户记忆都已预先加载在下方的上下文中
- 使用 `add_memory` 来存储带有结构化数据的新记忆卡
- 使用 `update_memory` 来修改现有记忆卡
- 使用 `delete_memory` 来删除过时的记忆卡

记忆卡使用分层结构：类别 -> 子类别 -> 键 -> 值

操作示例：
1. 添加记忆卡：
   content: {"category": "personal", "subcategory": "contact", "key": "email", "value": "user@example.com"}

2. 更新记忆卡：
   memory_id: "personal.contact.email"
   content: {"value": "newemail@example.com"}

3. 结构示例：
   - personal.preferences.coding_style -> "偏好函数式编程"
   - work.projects.current -> "开发AI聊天机器人"
   - family.children.xiaoming -> {"age": 8, "interests": ["足球", "阅读"]}"""

        elif self.config.memory_mode == MemoryMode.ADVANCED_JSON_CARDS:
            memory_instructions = """## 记忆管理：
- 所有用户记忆卡都已预先加载在下方的上下文中
- 使用 `add_memory` 来存储完整的记忆卡对象
- 使用 `update_memory` 来修改现有记忆卡
- 使用 `delete_memory` 来删除记忆卡

记忆卡是类别内的完整 JSON 对象。每张卡片必须包含：
- backstory：关于何时/为何获知此信息的上下文（1-2句话）
- date_created：当前时间戳（YYYY-MM-DD HH:MM:SS）
- person：此信息关联的人（例如："张三（主要用户）"、"王小美（女儿）"）
- relationship：角色/关系（例如："主要账户持有人"、"家庭成员"）
- 根据信息类型附加的相关字段

记忆卡操作示例：

1. 添加完整的记忆卡：
content: {
    "category": "financial",
    "card_key": "bank_account_primary",
    "card": {
        "backstory": "用户在设置自动账单支付时分享了银行详细信息",
        "date_created": "2024-01-15 10:30:00",
        "person": "张三（主要用户）",
        "relationship": "主要账户持有人",
        "bank_name": "中国工商银行",
        "account_type": "储蓄卡",
        "account_ending": "4567",
        "purpose": "用于支付账单的主卡"
    }
}

2. 添加医疗记忆卡：
content: {
    "category": "medical",
    "card_key": "doctor_dermatologist_xiaomei",
    "card": {
        "backstory": "用户需要为女儿的皮肤状况预约皮肤科医生",
        "date_created": "2024-01-16 14:00:00",
        "person": "王小美（女儿）",
        "relationship": "家庭成员",
        "doctor_name": "李医生",
        "specialty": "儿童皮肤科",
        "clinic": "儿童健康中心",
        "phone": "138-0000-1234",
        "condition_treated": "湿疹"
    }
}

重要提示：backstory 和 person 字段可以防止混淆。例如，如果没有正确的人员识别，
为儿童看病的皮肤科医生可能会被错误地建议用于年迈父母的阿尔茨海默病护理。"""

        else:
            memory_instructions = """## 记忆管理：
- 所有用户记忆都已预先加载在下方的上下文中
- 使用 `add_memory` 来存储关于用户的新重要信息
- 使用 `update_memory` 来修改现有记忆
- 使用 `delete_memory` 来删除过时或不正确的记忆"""

        system_content = base_prompt + memory_instructions + """

当前记忆上下文将随每条消息一起提供。"""

        self.conversation = [
            {
                "role": "system",
                "content": system_content
            }
        ]
    
    def _get_memory_context(self) -> str:
        """Get current memory context as a string"""
        context_parts = []
        
        # Add memory summary
        context_parts.append("=== USER MEMORIES ===")
        context_parts.append(self.memory_manager.get_context_string())
        context_parts.append("")
        
        # Add ALL conversation history if available
        if self.conversation_history and self.config.enable_conversation_history:
            # Get ALL conversation history, not just recent
            all_conversations = self.conversation_history.conversations if hasattr(self.conversation_history, 'conversations') else []
            
            if all_conversations:
                context_parts.append("=== FULL CONVERSATION HISTORY ===")
                context_parts.append(f"Total conversations: {len(all_conversations)}")
                context_parts.append("")
                
                for turn in all_conversations:
                    context_parts.append(f"[Session: {turn.session_id}, Turn {turn.turn_number}]")
                    context_parts.append(f"User: {turn.user_message}")
                    context_parts.append(f"Assistant: {turn.assistant_message}")
                    context_parts.append("")
        
        return "\n".join(context_parts)
    
    def _get_tools_description(self) -> List[Dict[str, Any]]:
        """Get tool descriptions for the model"""
        tools = []
        
        # Memory management tools
        if self.config.enable_memory_updates:
            tools.extend([
                {
                    "type": "function",
                    "function": {
                        "name": "add_memory",
                        "description": "Add a new memory about the user",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "The memory content to store"
                                },
                                "tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Optional tags for categorizing the memory"
                                }
                            },
                            "required": ["content"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "update_memory",
                        "description": "Update an existing memory",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "memory_id": {
                                    "type": "string",
                                    "description": "ID of the memory to update"
                                },
                                "content": {
                                    "type": "string",
                                    "description": "New content for the memory"
                                },
                                "tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Optional new tags"
                                }
                            },
                            "required": ["memory_id", "content"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "delete_memory",
                        "description": "Delete a memory",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "memory_id": {
                                    "type": "string",
                                    "description": "ID of the memory to delete"
                                }
                            },
                            "required": ["memory_id"]
                        }
                    }
                }
            ])
        
        return tools
    
    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[Any, Optional[str]]:
        """
        Execute a tool and return the result
        
        Returns:
            Tuple of (result, error_message)
        """
        try:
            if tool_name == "add_memory":
                result = self._tool_add_memory(**arguments)
            elif tool_name == "update_memory":
                result = self._tool_update_memory(**arguments)
            elif tool_name == "delete_memory":
                result = self._tool_delete_memory(**arguments)
            else:
                error = f"Unknown tool: {tool_name}"
                return {"error": error}, error
            
            return result, None
            
        except Exception as e:
            error_msg = f"Tool '{tool_name}' failed: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}, error_msg
    
    # Tool implementations
    def _tool_add_memory(self, content: Any, tags: List[str] = None) -> Dict[str, Any]:
        """Add a new memory"""
        if self.config.memory_mode in [MemoryMode.NOTES, MemoryMode.ENHANCED_NOTES]:
            # Both basic and enhanced notes use the same storage, just different prompts
            if isinstance(content, dict):
                # If content is a dict, extract string representation
                content_str = str(content)
            else:
                content_str = content
            
            memory_id = self.memory_manager.add_memory(
                content=content_str,
                session_id=self.session_id,
                tags=tags or []
            )
            
        elif self.config.memory_mode == MemoryMode.JSON_CARDS:
            # Basic JSON cards mode
            if isinstance(content, dict):
                # Content should already have the structure
                memory_content = content
            else:
                # Parse content to extract structure
                parts = str(content).split(':')
                if len(parts) >= 2:
                    category = "personal"
                    subcategory = "info"
                    key = parts[0].strip().replace(' ', '_').lower()
                    value = ':'.join(parts[1:]).strip()
                else:
                    category = "general"
                    subcategory = "notes"
                    key = f"note_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    value = content
                
                memory_content = {
                    'category': category,
                    'subcategory': subcategory,
                    'key': key,
                    'value': value
                }
            
            memory_id = self.memory_manager.add_memory(
                content=memory_content,
                session_id=self.session_id
            )
            
        elif self.config.memory_mode == MemoryMode.ADVANCED_JSON_CARDS:
            # Advanced JSON cards mode
            if not isinstance(content, dict):
                try:
                    content = json.loads(content)
                except:
                    return {
                        "success": False,
                        "message": "Advanced JSON cards mode requires properly structured JSON content"
                    }
            
            memory_id = self.memory_manager.add_memory(
                content=content,
                session_id=self.session_id
            )
        else:
            return {
                "success": False,
                "message": f"Unknown memory mode: {self.config.memory_mode}"
            }
        
        return {
            "success": True,
            "memory_id": memory_id,
            "message": f"Memory added successfully"
        }
    
    def _tool_update_memory(self, memory_id: str, content: Any, tags: List[str] = None) -> Dict[str, Any]:
        """Update an existing memory"""
        if self.config.memory_mode in [MemoryMode.NOTES, MemoryMode.ENHANCED_NOTES]:
            # Both basic and enhanced notes use the same storage
            if isinstance(content, dict):
                content_str = str(content)
            else:
                content_str = content
            
            success = self.memory_manager.update_memory(
                memory_id=memory_id,
                content=content_str,
                session_id=self.session_id,
                tags=tags
            )
            
        elif self.config.memory_mode == MemoryMode.JSON_CARDS:
            # Basic JSON cards mode
            if isinstance(content, dict):
                memory_content = content
            else:
                # For JSON cards, parse the memory_id and content
                parts = memory_id.split('.')
                if len(parts) == 3:
                    memory_content = {'value': content}
                else:
                    return {
                        "success": False,
                        "message": "Invalid memory_id format for JSON cards"
                    }
            
            success = self.memory_manager.update_memory(
                memory_id=memory_id,
                content=memory_content,
                session_id=self.session_id
            )
            
        elif self.config.memory_mode == MemoryMode.ADVANCED_JSON_CARDS:
            # Advanced JSON cards mode
            if not isinstance(content, dict):
                try:
                    content = json.loads(content)
                except:
                    return {
                        "success": False,
                        "message": "Advanced JSON cards mode requires properly structured JSON content"
                    }
            
            success = self.memory_manager.update_memory(
                memory_id=memory_id,
                content=content,
                session_id=self.session_id
            )
        else:
            success = False
        
        return {
            "success": success,
            "message": "Memory updated successfully" if success else "Memory not found"
        }
    
    def _tool_delete_memory(self, memory_id: str) -> Dict[str, Any]:
        """Delete a memory"""
        self.memory_manager.delete_memory(memory_id)
        return {
            "success": True,
            "message": f"Memory {memory_id} deleted"
        }
    
    def _save_trajectory(self, iteration: int, final_answer: Optional[str] = None):
        """Save current trajectory to file for debugging"""
        if not self.config.save_trajectory:
            return
        
        trajectory_data = {
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "model": self.model,
            "conversation": self.conversation,
            "tool_calls": [
                {
                    "tool_name": call.tool_name,
                    "arguments": call.arguments,
                    "result": call.result,
                    "error": call.error,
                    "timestamp": call.timestamp
                }
                for call in self.tool_calls
            ],
            "memory_state": self.memory_manager.get_context_string(),
            "final_answer": final_answer
        }
        
        try:
            with open(self.config.trajectory_file, 'w', encoding='utf-8') as f:
                json.dump(trajectory_data, f, indent=2, ensure_ascii=False)
            
            if self.verbose:
                logger.info(f"Trajectory saved to {self.config.trajectory_file}")
        except Exception as e:
            logger.warning(f"Failed to save trajectory: {e}")
    
    def execute_task(self, task: str, max_iterations: int = 15) -> Dict[str, Any]:
        """
        Execute a task using React pattern with tool calls and streaming support
        
        Args:
            task: The task/message from user
            max_iterations: Maximum number of tool call iterations
            
        Returns:
            Task execution result
        """
        # Add user message with memory context
        memory_context = self._get_memory_context()
        full_message = f"{task}\n\n{memory_context}"
        
        # Log the full prompt
        logger.info(f"User request: {task}")
        if memory_context:
            logger.info(f"Memory context added: {memory_context}")
        
        self.conversation.append({"role": "user", "content": full_message})
        
        iteration = 0
        final_answer = None
        
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Iteration {iteration}/{max_iterations}")
            
            # Save trajectory
            self._save_trajectory(iteration)
            
            logger.info(f"Sending streaming request to {self.provider.upper()} API")
            logger.info(f"Full conversation: {self.conversation}")
            logger.info(f"Tools available: {self._get_tools_description()}")
            
            try:
                # Create streaming response
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.conversation,
                    tools=self._get_tools_description(),
                    tool_choice="auto",
                    temperature=_reasoning_safe_temperature(self.model, 0.3),
                    max_tokens=4096,
                    stream=True  # Enable streaming
                )
                
                # Collect streaming data
                collected_content = []
                current_tool_calls = []
                
                # Process the stream
                collected_reasoning = []  # Separate collection for reasoning content
                
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta:
                        delta = chunk.choices[0].delta
                        
                        # Handle reasoning field (for o1 models and similar)
                        if hasattr(delta, 'reasoning') and delta.reasoning:
                            reasoning = delta.reasoning
                            collected_reasoning.append(reasoning)
                            
                            # Stream reasoning to console if verbose
                            if self.verbose:
                                if len(collected_reasoning) == 1:  # First reasoning chunk
                                    print("\n🤔 Reasoning: ", end="", flush=True)
                                print(reasoning, end="", flush=True)
                        
                        # Handle regular content streaming
                        if hasattr(delta, 'content') and delta.content:
                            content = delta.content
                            collected_content.append(content)
                            
                            # Stream to console if verbose
                            if self.verbose:
                                if len(collected_content) == 1 and not collected_reasoning:  # First content chunk
                                    print("\nAssistant: ", end="", flush=True)
                                print(content, end="", flush=True)
                        
                        # Handle tool calls in streaming
                        if hasattr(delta, 'tool_calls') and delta.tool_calls:
                            for tool_call_delta in delta.tool_calls:
                                if tool_call_delta.index is not None:
                                    # Ensure we have enough tool calls in the list
                                    while len(current_tool_calls) <= tool_call_delta.index:
                                        current_tool_calls.append({
                                            "id": "",
                                            "type": "function",
                                            "function": {"name": "", "arguments": ""}
                                        })
                                    
                                    # Update tool call data
                                    if tool_call_delta.id:
                                        current_tool_calls[tool_call_delta.index]["id"] = tool_call_delta.id
                                    if tool_call_delta.function:
                                        if tool_call_delta.function.name:
                                            current_tool_calls[tool_call_delta.index]["function"]["name"] = tool_call_delta.function.name
                                            # Print tool call name when first detected
                                            if self.verbose:
                                                print(f"\n🔧 Tool Call [{tool_call_delta.index}]: {tool_call_delta.function.name}", end="", flush=True)
                                        if tool_call_delta.function.arguments:
                                            current_tool_calls[tool_call_delta.index]["function"]["arguments"] += tool_call_delta.function.arguments
                                            # Stream tool arguments in verbose mode
                                            if self.verbose:
                                                # Print arguments as they stream (they come in chunks)
                                                print(tool_call_delta.function.arguments, end="", flush=True)
                
                # Add newline after streaming content, reasoning or tool calls
                if self.verbose and (collected_content or collected_reasoning or current_tool_calls):
                    print()  # New line after streaming
                
                # Construct complete message matching OpenAI API structure
                # Keep reasoning, content, and tool_calls as separate fields
                complete_message = {
                    "role": "assistant"
                }
                
                # Add reasoning field if present
                if collected_reasoning:
                    reasoning_text = "".join(collected_reasoning)
                    complete_message["reasoning"] = reasoning_text
                
                # Add content field if present
                if collected_content:
                    complete_message["content"] = "".join(collected_content)
                else:
                    complete_message["content"] = None
                
                # Add tool_calls field if present
                if current_tool_calls:
                    complete_message["tool_calls"] = current_tool_calls
                
                # Always append the message if it has reasoning, content, or tool calls
                # This preserves all assistant output including reasoning
                if complete_message.get("reasoning") or complete_message.get("content") or current_tool_calls:
                    self.conversation.append(complete_message)
                
                # Handle tool calls if present
                if current_tool_calls:
                    for tool_call in current_tool_calls:
                        function_name = tool_call["function"]["name"]
                        # The assistant message with tool_calls is already in
                        # self.conversation; bailing out on malformed arguments
                        # would leave this tool_call_id unanswered and every
                        # later request would be rejected by the provider.
                        # Answer it with an error message instead.
                        try:
                            function_args = json.loads(tool_call["function"]["arguments"] or "{}")
                        except json.JSONDecodeError as exc:
                            error_msg = f"Invalid tool arguments (not valid JSON): {exc}"
                            logger.info(f"  ❌ Error: {error_msg}")
                            if self.verbose:
                                print(f"\n  ❌ Tool Error: {error_msg}")
                            self.conversation.append({
                                "role": "tool",
                                "tool_call_id": tool_call["id"],
                                "content": json.dumps({"error": error_msg})
                            })
                            continue

                        # Track tool call count
                        self.tool_call_counts[function_name] = self.tool_call_counts.get(function_name, 0) + 1
                        call_number = self.tool_call_counts[function_name]
                        
                        logger.info(f"Executing tool: {function_name} (call #{call_number})")
                        if self.verbose:
                            print(f"\n⚡ Executing: {function_name} (call #{call_number})")
                        
                        # Execute the tool
                        result, error = self._execute_tool(function_name, function_args)
                        
                        # Log and display result
                        if error:
                            logger.info(f"  ❌ Error: {error}")
                            if self.verbose:
                                print(f"\n  ❌ Tool Error: {error}")
                        else:
                            logger.info(f"  ✅ Success: {json.dumps(result)[:200]}")
                            if self.verbose:
                                result_str = json.dumps(result, ensure_ascii=False)
                                if len(result_str) > 200:
                                    result_str = result_str[:200] + "..."
                                print(f"\n  ✅ Tool Result: {result_str}")
                        
                        # Record tool call
                        tool_call_record = ToolCall(
                            tool_name=function_name,
                            arguments=function_args,
                            result=result if not error else None,
                            error=error
                        )
                        self.tool_calls.append(tool_call_record)
                        
                        # Add tool result to conversation
                        self.conversation.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps(result)
                        })
                    
                    # Continue to next iteration for more processing
                    continue
                
                elif complete_message.get("content") or complete_message.get("reasoning"):
                    # No tool calls but has content or reasoning - this is the final answer
                    # Prioritize content over reasoning for the final answer
                    final_answer = complete_message.get("content") or complete_message.get("reasoning")
                    
                    # Log both reasoning and content if present
                    if complete_message.get("reasoning") and complete_message.get("content"):
                        logger.info(f"Response complete with reasoning and content")
                    else:
                        logger.info(f"Response complete (no more tool calls): {final_answer}")
                    
                    # Save conversation to history (use content if available, otherwise reasoning)
                    if self.conversation_history:
                        self.conversation_history.add_turn(
                            session_id=self.session_id,
                            user_message=task,
                            assistant_message=final_answer
                        )
                    
                    # Save final trajectory
                    self._save_trajectory(iteration, final_answer)
                    break  # Break when no more tool calls
                    
            except Exception as e:
                logger.error(f"Error during streaming task execution: {str(e)}")
                self._save_trajectory(iteration)
                return {
                    "error": str(e),
                    "tool_calls": self.tool_calls,
                    "iterations": iteration,
                    "trajectory_file": self.config.trajectory_file if self.config.save_trajectory else None
                }
        
        # Save final trajectory
        self._save_trajectory(iteration, final_answer)
        
        # Prepare result with all relevant information
        result = {
            "final_answer": final_answer,
            "tool_calls": self.tool_calls,
            "iterations": iteration,
            "success": final_answer is not None,
            "memory_state": self.memory_manager.get_context_string(),
            "trajectory_file": self.config.trajectory_file if self.config.save_trajectory else None
        }
        
        # Include reasoning if it was collected in the last message
        if self.conversation and isinstance(self.conversation[-1], dict):
            last_message = self.conversation[-1]
            if last_message.get("role") == "assistant" and last_message.get("reasoning"):
                result["reasoning"] = last_message["reasoning"]
        
        return result
    
    def chat(self, message: str, stream: bool = False) -> str:
        """
        Simple chat interface (wraps execute_task for compatibility)
        
        Args:
            message: User message
            stream: Whether to stream the response (only works when tools are disabled)
            
        Returns:
            Assistant response
        """
        if stream and not self.config.enable_memory_updates:
            # Stream response when tools are disabled
            return self._chat_stream(message)
        else:
            # Use regular execution with tools
            result = self.execute_task(message)
            return result.get('final_answer', result.get('error', 'I apologize, but I was unable to generate a response.'))
    
    def _chat_stream(self, message: str) -> str:
        """
        Stream chat response (only when tools are disabled)
        
        Args:
            message: User message
            
        Returns:
            Assistant response
        """
        # Get memory context
        memory_context = self._get_memory_context()
        
        if memory_context:
            full_message = f"Current Memory Context:\n{memory_context}\n\nUser Message: {message}"
        else:
            full_message = message
        
        # Log the full prompt
        logger.info(f"User request: {message}")
        if memory_context:
            logger.info(f"Memory context added: {memory_context}")
        logger.info(f"Full prompt sent to API (streaming): {full_message}")
        
        # Add to conversation
        self.conversation.append({"role": "user", "content": full_message})
        
        try:
            # Stream the response
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation,
                temperature=_reasoning_safe_temperature(self.model, 0.3),
                max_tokens=4096,
                stream=True
            )
            
            # Collect and stream response
            assistant_message = ""
            logger.info("Streaming response...")
            print("\nAssistant: ", end='', flush=True)
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    assistant_message += delta
                    # Stream output in real-time
                    print(delta, end='', flush=True)
            
            print()  # New line after streaming
            
            # Log the complete response
            logger.info(f"Assistant response (streamed): {assistant_message}")
            
            # Add to conversation
            self.conversation.append({"role": "assistant", "content": assistant_message})
            
            # Save to history if available
            if self.conversation_history:
                self.conversation_history.add_turn(
                    session_id=self.session_id,
                    user_message=message,
                    assistant_message=assistant_message
                )
            
            return assistant_message
            
        except Exception as e:
            logger.error(f"Error during streaming: {str(e)}")
            return f"Error: {str(e)}"
    
    def reset(self):
        """Reset the agent's state for a new conversation"""
        self.tool_calls = []
        self.tool_call_counts = {}
        self.session_id = self._start_session()
        self._init_system_prompt()
        logger.info("Agent state reset")
