"""
事件驱动 AI Agent（带系统提示功能）
可响应来自多种来源的事件，同时保持所有系统提示功能。
"""

import json
import os
import sys
import subprocess
import platform
import logging
import concurrent.futures
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import requests
import traceback
import tempfile
import shutil
from pathlib import Path

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from llm.client import get_llm_client
from event_types import Event, EventType
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent


def _reasoning_safe_temperature(model, requested=1.0):
    """
    推理模型（Kimi K3、GPT-5 等）只接受 temperature=1。
    对于这些模型返回 1，否则返回请求的值（适用于豆包、DeepSeek、旧版月之暗面等非推理提供商）。
    """
    m = str(model or "").lower().replace("/", "-")
    return 1 if ("kimi-k3" in m or "gpt-5" in m) else requested


def get_client_from_config(provider: Optional[str] = None, model: Optional[str] = None):
    """
    根据配置获取 LLM 客户端

    Args:
        provider: 可选的提供商覆盖
        model: 可选的模型覆盖

    Returns:
        (client, provider, model): 客户端实例和实际使用的提供商/模型
    """
    try:
        client = get_llm_client()
        return client, client.provider, client.model_name
    except Exception as e:
        logger.warning(f"无法获取 LLM 客户端: {e}")
        return None, provider or os.getenv("LLM_PROVIDER", "kimi"), model


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TodoStatus(Enum):
    """Status of a TODO item"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class TodoItem:
    """Represents a single TODO item"""
    id: int
    content: str
    status: TodoStatus = TodoStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = None


@dataclass
class ToolCall:
    """Represents a single tool call with enhanced tracking"""
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    call_number: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: Optional[int] = None


@dataclass
class SystemHintConfig:
    """Configuration for system hints"""
    enable_timestamps: bool = True
    enable_tool_counter: bool = True
    enable_todo_list: bool = True
    enable_detailed_errors: bool = True
    enable_system_state: bool = True
    timestamp_format: str = "%Y-%m-%d %H:%M:%S"
    simulate_time_delay: bool = False
    save_trajectory: bool = True
    trajectory_file: str = "trajectory.json"
    # Model configuration (matching conversational_agent.py)
    temperature: float = 0.7
    max_tokens: int = 4096
    # MCP server configuration
    use_mcp_servers: bool = False  # Disabled by default - requires async setup
    mcp_collaboration_tools_path: str = "../collaboration-tools/src/main.py"
    mcp_execution_tools_path: str = "../execution-tools/server.py"
    mcp_perception_tools_path: str = "../perception-tools/src/main.py"


class MCPServerManager:
    """管理与多个 MCP 服务器的连接"""

    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self.tools: Dict[str, Any] = {}
        self.server_contexts = []  # 存储上下文管理器以便正确清理

    async def connect_server(self, name: str, script_path: str) -> bool:
        """
        连接到 MCP 服务器，并进行适当的错误隔离

        注意：此方法仅存储工具元数据。对于实际工具执行，
        需要以不同方式生成 MCP 服务器或使用内置工具。

        Args:
            name: 服务器名称
            script_path: MCP 服务器脚本的路径

        Returns:
            如果连接成功则返回 True，否则返回 False
        """
        try:
            # 检查脚本是否存在
            if not os.path.exists(script_path):
                logger.warning(f"未找到 MCP 服务器脚本: {script_path}")
                return False

            logger.info(f"正在从 MCP 服务器 '{name}' 发现工具，路径: {script_path}")

            server_params = StdioServerParameters(
                command=sys.executable,
                args=[script_path],
                env=os.environ.copy()  # 传递环境变量
            )

            # 使用临时连接仅用于发现工具
            # 实际工具执行将按需生成服务器
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # 发现工具
                    tools_result = await session.list_tools()
                    tools = tools_result.tools

                    # 存储工具元数据（而非实时会话）
                    for tool in tools:
                        # 使用下划线分隔符以获得有效的函数名
                        # OpenAI 兼容的 API 拒绝包含点的名称
                        tool_key = f"{name}_{tool.name}"
                        self.tools[tool_key] = {
                            "server": name,
                            "tool": tool,
                            "script_path": script_path,
                            "server_params": server_params
                        }

                    logger.info(f"✅ 从 '{name}' 发现工具: {len(tools)} 个工具")
                    return True

        except Exception as e:
            logger.warning(f"从 '{name}' 发现工具失败: {str(e)[:100]}")
            return False

    async def call_tool(self, tool_key: str, arguments: Dict[str, Any]) -> Any:
        """
        通过生成新的服务器连接来调用 MCP 工具

        Args:
            tool_key: 格式为 "server.tool_name" 的工具键
            arguments: 工具参数

        Returns:
            工具结果
        """
        if tool_key not in self.tools:
            raise ValueError(f"未知的 MCP 工具: {tool_key}")

        tool_info = self.tools[tool_key]
        tool = tool_info["tool"]
        server_params = tool_info["server_params"]

        try:
            # 为此工具调用生成新连接
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool.name, arguments)

                    # 从结果中提取文本内容
                    text_content = []
                    if hasattr(result, 'content'):
                        for c in result.content:
                            if isinstance(c, TextContent):
                                text_content.append(c.text)

                    return {
                        "success": True,
                        "result": "\n".join(text_content) if text_content else str(result)
                    }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def disconnect_all(self):
        """
        清理 MCP 管理器（没有持久连接需要关闭）

        由于我们为每次工具调用生成新连接，
        因此没有什么需要断开连接的。
        """
        logger.info("MCP 管理器清理完成（无持久连接）")
        self.sessions.clear()
        self.tools.clear()
        self.server_contexts.clear()


class EventTriggeredAgent:
    """
    事件驱动 AI Agent（带系统提示功能）
    响应事件的同时保持所有系统提示功能
    """

    def __init__(self, api_key: Optional[str] = None, provider: Optional[str] = None,
                 model: Optional[str] = None, config: Optional[SystemHintConfig] = None,
                 verbose: bool = True):
        """
        初始化事件驱动 Agent

        Args:
            api_key: 已废弃，保留以兼容旧代码（现在从项目根目录 .env 读取）
            provider: 可选的提供商覆盖（从 .env 读取）
            model: 可选的模型覆盖（从 .env 读取）
            config: 系统提示配置
            verbose: 如果为 True，记录完整日志
        """
        self.verbose = verbose
        self.config = config or SystemHintConfig()

        # 使用统一 LLM 客户端
        client, actual_provider, actual_model = get_client_from_config(provider, model)

        if client is None:
            raise ValueError(
                "无法初始化 LLM 客户端。请检查项目根目录 .env 文件中的配置。"
            )

        self.client = client
        self.provider = actual_provider
        self.model = actual_model

        # 初始化跟踪
        self.tool_call_counts: Dict[str, int] = {}
        self.tool_calls: List[ToolCall] = []
        self.todo_list: List[TodoItem] = []
        self.next_todo_id = 1

        # 初始化对话历史
        self.conversation_history = []
        self.simulated_time = datetime.now()
        self._init_system_prompt()

        # 跟踪当前工作目录
        self.current_directory = os.getcwd()

        # 事件跟踪
        self.last_user_interaction = datetime.now()
        self.background_processes: Dict[str, Dict[str, Any]] = {}

        # 初始化 MCP 服务器管理器
        self.mcp_manager = MCPServerManager()
        self.mcp_tools_loaded = False

        logger.info(f"事件驱动 Agent 初始化完成 - 提供商: {self.provider}, 模型: {self.model}")
        logger.info("注意: 调用 load_mcp_tools() 连接到 MCP 服务器")
    
    async def load_mcp_tools(self):
        """
        从 MCP 服务器加载工具

        必须在 Agent 初始化后的异步上下文中调用此方法。
        """
        if not self.config.use_mcp_servers:
            logger.info("配置中已禁用 MCP 服务器")
            return

        logger.info("正在从 MCP 服务器加载工具...")

        # 获取 Agent 脚本所在的目录
        agent_dir = os.path.dirname(os.path.abspath(__file__))

        # 尝试连接到 collaboration-tools
        collab_path = os.path.join(agent_dir, self.config.mcp_collaboration_tools_path)
        collab_loaded = await self.mcp_manager.connect_server("collaboration", collab_path)

        # 尝试连接到 execution-tools
        exec_path = os.path.join(agent_dir, self.config.mcp_execution_tools_path)
        exec_loaded = await self.mcp_manager.connect_server("execution", exec_path)

        # 尝试连接到 perception-tools
        percept_path = os.path.join(agent_dir, self.config.mcp_perception_tools_path)
        percept_loaded = await self.mcp_manager.connect_server("perception", percept_path)

        # 如果加载了任何工具，则设置标志
        self.mcp_tools_loaded = collab_loaded or exec_loaded or percept_loaded

        if self.mcp_tools_loaded:
            logger.info(f"✅ MCP 工具已加载: {len(self.mcp_manager.tools)} 个工具可用")
            logger.info(f"   可用的 MCP 工具: {list(self.mcp_manager.tools.keys())[:5]}...")
        else:
            logger.info("⚠️  未找到 MCP 服务器，仅使用内置工具")
    
    def _init_system_prompt(self):
        """初始化对话的系统提示词"""
        system_content = """你是一个智能助手，可以使用各种工具进行文件操作、代码执行和系统命令。

你会响应来自多种来源的事件：
- 来自 Web 界面和即时通讯的用户消息
- 邮件回复和 GitHub 通知
- 系统提醒和超时警报
- 定时器触发和进程监控事件

你的任务是使用可用工具高效地完成给定的目标。逐步思考并根据需要使用工具。

## TODO 列表管理规则：
- 对于任何有 3 个以上步骤的复杂任务，立即使用 `rewrite_todo_list` 创建 TODO 列表
- 将用户的请求分解为具体、可执行的 TODO 项
- 开始处理 TODO 项时，使用 `update_todo_status` 将其更新为 'in_progress'
- 完成项目后立即标记为 'completed'
- 同时只能有一个项目处于 'in_progress' 状态
- 如果遇到错误或需要改变方法，将相关的 TODO 更新为 'cancelled' 并添加新的
- 使用 TODO 列表作为你的主要规划和跟踪机制
- 讨论进度时引用 TODO 项目的 ID

## 关键行为：
1. 复杂任务始终从创建 TODO 列表开始
2. 注意时间戳以理解事件的时间线
3. 注意工具调用编号（例如"工具调用 #3"）以避免重复循环 - 如果看到高编号，改变策略
4. 从详细错误消息中学习以解决问题并调整方法
5. 了解系统状态中显示的当前目录和系统环境
6. 探索项目时，系统阅读关键文件（README、main.py、agent.py）以了解结构

## 事件响应指南：
- 在响应中确认事件来源
- 对于超时事件，主动检查状态并采取适当行动
- 对于系统警报，在响应前调查问题
- 在来自同一对话的多个事件之间保持上下文

## 错误处理：
- 仔细阅读错误消息 - 它们包含关于出了什么问题的具体信息
- 使用错误消息中提供的建议来解决问题
- 如果工具多次失败（检查调用编号），尝试不同的方法
- 常见修复：检查文件路径、验证当前目录、确保适当的权限

重要：完成所有任务后，清楚地声明"最终答案："后跟已完成的全面总结。"""

        self.conversation_history = [
            {
                "role": "system",
                "content": system_content
            }
        ]
    
    def _get_system_state(self) -> str:
        """Get current system state information"""
        if not self.config.enable_system_state:
            return ""
        
        # Detect OS
        system = platform.system()
        if system == "Windows":
            shell_type = "Windows Command Prompt or PowerShell"
        elif system == "Darwin":
            shell_type = "macOS Terminal (zsh/bash)"
        else:
            shell_type = f"Linux Shell ({os.environ.get('SHELL', 'bash')})"
        
        state_info = [
            f"Current Time: {self._get_timestamp()}",
            f"Current Directory: {self.current_directory}",
            f"System: {system} ({platform.release()})",
            f"Shell Environment: {shell_type}",
            f"Python Version: {sys.version.split()[0]}"
        ]
        
        # Add background process info if any
        if self.background_processes:
            state_info.append(f"Background Processes: {len(self.background_processes)} active")
        
        return "\n".join(state_info)
    
    def _get_timestamp(self) -> str:
        """Get formatted timestamp"""
        if self.config.simulate_time_delay:
            return self.simulated_time.strftime(self.config.timestamp_format)
        return datetime.now().strftime(self.config.timestamp_format)
    
    def _advance_simulated_time(self, hours: int = 0, minutes: int = 0, seconds: int = 30):
        """Advance simulated time for demo purposes"""
        if self.config.simulate_time_delay:
            self.simulated_time += timedelta(hours=hours, minutes=minutes, seconds=seconds)
    
    def _save_trajectory(self, iteration: int, final_answer: Optional[str] = None):
        """Save current trajectory to JSON file for debugging"""
        if not self.config.save_trajectory:
            return
        
        trajectory_data = {
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "provider": self.provider,
            "model": self.model,
            "conversation_history": self.conversation_history,
            "tool_calls": [
                {
                    "tool_name": call.tool_name,
                    "arguments": call.arguments,
                    "result": call.result,
                    "error": call.error,
                    "call_number": call.call_number,
                    "timestamp": call.timestamp,
                    "duration_ms": call.duration_ms
                }
                for call in self.tool_calls
            ],
            "todo_list": [
                {
                    "id": item.id,
                    "content": item.content,
                    "status": item.status.value,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at
                }
                for item in self.todo_list
            ],
            "current_directory": self.current_directory,
            "final_answer": final_answer,
            "background_processes": self.background_processes,
            "config": {
                "enable_timestamps": self.config.enable_timestamps,
                "enable_tool_counter": self.config.enable_tool_counter,
                "enable_todo_list": self.config.enable_todo_list,
                "enable_detailed_errors": self.config.enable_detailed_errors,
                "enable_system_state": self.config.enable_system_state,
                "timestamp_format": self.config.timestamp_format,
                "simulate_time_delay": self.config.simulate_time_delay
            }
        }
        
        try:
            with open(self.config.trajectory_file, 'w', encoding='utf-8') as f:
                json.dump(trajectory_data, f, indent=2, ensure_ascii=False)
            
            if self.verbose:
                logger.info(f"Trajectory saved to {self.config.trajectory_file} (iteration {iteration})")
        except Exception as e:
            logger.warning(f"Failed to save trajectory: {e}")
    
    def _format_todo_list(self) -> str:
        """Format TODO list for display"""
        if not self.todo_list:
            return "TODO List: Empty"
        
        lines = ["TODO List:"]
        for item in self.todo_list:
            status_symbol = {
                TodoStatus.PENDING: "⏳",
                TodoStatus.IN_PROGRESS: "🔄",
                TodoStatus.COMPLETED: "✅",
                TodoStatus.CANCELLED: "❌"
            }.get(item.status, "❓")
            
            lines.append(f"  [{item.id}] {status_symbol} {item.content} ({item.status.value})")
        
        return "\n".join(lines)
    
    def _get_system_hint(self) -> Optional[str]:
        """Get system hint content with current state"""
        if not any([self.config.enable_system_state, self.config.enable_todo_list]):
            return None
        
        hint_parts = []
        
        if self.config.enable_system_state:
            hint_parts.append("=== SYSTEM STATE ===")
            hint_parts.append(self._get_system_state())
            hint_parts.append("")
        
        if self.config.enable_todo_list and self.todo_list:
            hint_parts.append("=== CURRENT TASKS ===")
            hint_parts.append(self._format_todo_list())
            hint_parts.append("")
        
        if hint_parts:
            return "\n".join(hint_parts)
        return None
    
    def _get_tools_description(self) -> List[Dict[str, Any]]:
        """Get tool descriptions for the model"""
        tools = []
        
        # Add MCP tools if available
        if self.mcp_tools_loaded:
            for tool_key, tool_info in self.mcp_manager.tools.items():
                mcp_tool = tool_info["tool"]
                
                # Convert MCP tool schema to OpenAI function format
                tool_desc = {
                    "type": "function",
                    "function": {
                        "name": tool_key,  # Use prefixed name (e.g., "collaboration.mcp_browser_navigate")
                        "description": mcp_tool.description or mcp_tool.name,
                        "parameters": mcp_tool.inputSchema if hasattr(mcp_tool, 'inputSchema') else {
                            "type": "object",
                            "properties": {}
                        }
                    }
                }
                tools.append(tool_desc)
        else:
            # Fallback to built-in tools if MCP servers not available
            tools.extend([
                {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "Read the contents of a text file. Returns error for binary files. Supports partial reading for large files.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "Path to the file to read (absolute or relative to current directory)"
                                },
                                "begin_line": {
                                    "type": "integer",
                                    "description": "Optional: Line number to start reading from (1-based indexing)"
                                },
                                "number_lines": {
                                    "type": "integer",
                                    "description": "Optional: Number of lines to read from begin_line"
                                }
                            },
                            "required": ["file_path"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "description": "Write content to a file (creates or overwrites)",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "Path to the file to write"
                                },
                                "content": {
                                    "type": "string",
                                    "description": "Content to write to the file"
                                }
                            },
                            "required": ["file_path", "content"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "code_interpreter",
                        "description": "Execute Python code in a restricted environment",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "code": {
                                    "type": "string",
                                    "description": "Python code to execute"
                                }
                            },
                            "required": ["code"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "execute_command",
                        "description": "Execute a shell command in the current directory",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "command": {
                                    "type": "string",
                                    "description": "Shell command to execute"
                                },
                                "working_dir": {
                                    "type": "string",
                                    "description": "Optional working directory for the command"
                                }
                            },
                            "required": ["command"]
                        }
                    }
                }
            ])
        
        # Always add TODO management tools if enabled
        if self.config.enable_todo_list:
            tools.extend([
                {
                    "type": "function",
                    "function": {
                        "name": "rewrite_todo_list",
                        "description": "Rewrite the TODO list with new pending items (keeps completed/cancelled items)",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "items": {
                                    "type": "array",
                                    "items": {
                                        "type": "string"
                                    },
                                    "description": "List of new TODO items to add as pending"
                                }
                            },
                            "required": ["items"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "update_todo_status",
                        "description": "Update the status of existing TODO items",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "updates": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "id": {
                                                "type": "integer",
                                                "description": "TODO item ID"
                                            },
                                            "status": {
                                                "type": "string",
                                                "enum": ["pending", "in_progress", "completed", "cancelled"],
                                                "description": "New status for the item"
                                            }
                                        },
                                        "required": ["id", "status"]
                                    },
                                    "description": "List of TODO items to update with their new status"
                                }
                            },
                            "required": ["updates"]
                        }
                    }
                }
            ])
        
        return tools
    
    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[Any, Optional[str]]:
        """Execute a tool and return the result with detailed error information"""
        start_time = datetime.now()
        
        try:
            # Check if it's an MCP tool (prefixed with server name using underscore)
            if "_" in tool_name and tool_name in self.mcp_manager.tools:
                # Execute MCP tool asynchronously
                # Check if there's already a running event loop
                try:
                    loop = asyncio.get_running_loop()
                    # If we're already in an async context, we can't use asyncio.run()
                    # Create a new event loop in a separate thread
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            self.mcp_manager.call_tool(tool_name, arguments)
                        )
                        result = future.result()
                except RuntimeError:
                    # No event loop running, safe to use asyncio.run()
                    result = asyncio.run(self.mcp_manager.call_tool(tool_name, arguments))
                
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                return result, None if result.get("success") else result.get("error")
            
            # Built-in tools
            if tool_name == "read_file":
                result = self._tool_read_file(**arguments)
            elif tool_name == "write_file":
                result = self._tool_write_file(**arguments)
            elif tool_name == "code_interpreter":
                result = self._tool_code_interpreter(**arguments)
            elif tool_name == "execute_command":
                result = self._tool_execute_command(**arguments)
            elif tool_name == "rewrite_todo_list":
                result = self._tool_rewrite_todo_list(**arguments)
            elif tool_name == "update_todo_status":
                result = self._tool_update_todo_status(**arguments)
            else:
                error = f"Unknown tool: {tool_name}"
                return {"error": error}, error
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return result, None
            
        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            error_detail = self._get_detailed_error(e, tool_name, arguments)
            
            if self.config.enable_detailed_errors:
                return {"error": error_detail}, error_detail
            else:
                return {"error": str(e)}, str(e)
    
    def _get_detailed_error(self, exception: Exception, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Get detailed error information for debugging"""
        error_parts = [
            f"Tool '{tool_name}' failed with {type(exception).__name__}: {str(exception)}",
            f"Arguments: {json.dumps(arguments, indent=2)}",
        ]
        
        if self.verbose:
            tb = traceback.format_exc()
            error_parts.append(f"Traceback:\n{tb}")
        
        suggestions = self._get_error_suggestions(exception, tool_name)
        if suggestions:
            error_parts.append(f"Suggestions: {suggestions}")
        
        return "\n".join(error_parts)
    
    def _get_error_suggestions(self, exception: Exception, tool_name: str) -> str:
        """Get suggestions for fixing common errors"""
        error_str = str(exception).lower()
        exception_type = type(exception).__name__
        
        suggestions = []
        
        if "permission" in error_str or exception_type == "PermissionError":
            suggestions.append("Check file/directory permissions")
            suggestions.append("Try using a different directory or running with appropriate permissions")
        elif "not found" in error_str or "no such file" in error_str or exception_type == "FileNotFoundError":
            suggestions.append("Verify the file/directory path exists")
            suggestions.append("Check the current working directory")
            suggestions.append("Use absolute paths or create the file/directory first")
        elif "syntax" in error_str or exception_type == "SyntaxError":
            suggestions.append("Check the code syntax")
            suggestions.append("Ensure proper indentation and valid Python syntax")
        elif "timeout" in error_str:
            suggestions.append("The operation took too long")
            suggestions.append("Try with simpler input or break into smaller steps")
        elif "import" in error_str or exception_type == "ImportError":
            suggestions.append("Required module not available in restricted environment")
            suggestions.append("Use only built-in Python modules")
        
        return " | ".join(suggestions) if suggestions else ""
    
    # Tool implementations (copied from original agent.py)
    def _tool_read_file(self, file_path: str, begin_line: Optional[int] = None, 
                       number_lines: Optional[int] = None) -> Dict[str, Any]:
        """Read file contents with optional line-based reading"""
        try:
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.current_directory, file_path)
            
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # Check if it's a binary file
            try:
                with open(file_path, 'rb') as f:
                    chunk = f.read(1024)
                    if b'\x00' in chunk:
                        return {
                            "success": False,
                            "error": "Cannot read binary file. This tool only supports text files.",
                            "file_path": file_path,
                            "is_binary": True
                        }
                    try:
                        chunk.decode('utf-8')
                    except UnicodeDecodeError:
                        return {
                            "success": False,
                            "error": "File is not a valid text file (encoding error).",
                            "file_path": file_path,
                            "is_binary": True
                        }
            except Exception as e:
                raise
            
            with open(file_path, 'r', encoding='utf-8') as f:
                if begin_line is not None or number_lines is not None:
                    all_lines = f.readlines()
                    total_lines = len(all_lines)
                    
                    start_line = (begin_line - 1) if begin_line is not None else 0
                    if start_line < 0:
                        start_line = 0
                    if start_line >= total_lines:
                        return {
                            "success": False,
                            "error": f"begin_line {begin_line} is beyond file length ({total_lines} lines)",
                            "file_path": file_path,
                            "total_lines": total_lines
                        }
                    
                    if number_lines is not None:
                        end_line = min(start_line + number_lines, total_lines)
                    else:
                        end_line = total_lines
                    
                    selected_lines = all_lines[start_line:end_line]
                    content = ''.join(selected_lines)
                    
                    stat = os.stat(file_path)
                    
                    return {
                        "success": True,
                        "file_path": file_path,
                        "content": content,
                        "size_bytes": stat.st_size,
                        "total_lines": total_lines,
                        "begin_line": start_line + 1,
                        "end_line": end_line,
                        "lines_read": len(selected_lines),
                        "partial_read": True
                    }
                else:
                    content = f.read()
                    stat = os.stat(file_path)
                    
                    return {
                        "success": True,
                        "file_path": file_path,
                        "content": content,
                        "size_bytes": stat.st_size,
                        "lines": len(content.splitlines()),
                        "partial_read": False
                    }
        except Exception as e:
            raise
    
    def _tool_write_file(self, file_path: str, content: str) -> Dict[str, Any]:
        """Write content to file"""
        try:
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.current_directory, file_path)
            
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {
                "success": True,
                "file_path": file_path,
                "bytes_written": len(content.encode('utf-8')),
                "lines_written": len(content.splitlines())
            }
        except Exception as e:
            raise
    
    def _tool_code_interpreter(self, code: str) -> Dict[str, Any]:
        """Execute Python code in restricted environment"""
        try:
            import io
            import contextlib
            
            output_buffer = io.StringIO()
            error_buffer = io.StringIO()
            
            # Use one namespace so functions defined by the snippet can resolve
            # names assigned earlier in the same snippet.
            exec_ns = {}
            with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
                exec(code, exec_ns)
            
            stdout = output_buffer.getvalue()
            stderr = error_buffer.getvalue()
            
            return {
                "success": True,
                "stdout": stdout,
                "stderr": stderr,
            }
        except Exception as e:
            raise
    
    def _tool_execute_command(self, command: str, working_dir: Optional[str] = None) -> Dict[str, Any]:
        """Execute shell command"""
        try:
            if working_dir is None:
                working_dir = self.current_directory
            elif not os.path.isabs(working_dir):
                working_dir = os.path.join(self.current_directory, working_dir)
            
            if command.strip().startswith('cd '):
                new_dir = command.strip()[3:].strip()
                if not os.path.isabs(new_dir):
                    new_dir = os.path.join(self.current_directory, new_dir)
                
                if os.path.isdir(new_dir):
                    self.current_directory = os.path.abspath(new_dir)
                    return {
                        "success": True,
                        "command": command,
                        "output": f"Changed directory to: {self.current_directory}",
                        "return_code": 0
                    }
                else:
                    raise FileNotFoundError(f"Directory not found: {new_dir}")
            
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=working_dir,
                timeout=30
            )
            
            return {
                "success": result.returncode == 0,
                "command": command,
                "output": result.stdout,
                "error": result.stderr if result.stderr else None,
                "return_code": result.returncode,
                "working_dir": working_dir
            }
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Command timed out after 30 seconds: {command}")
        except Exception as e:
            raise
    
    def _tool_rewrite_todo_list(self, items: List[str]) -> Dict[str, Any]:
        """Rewrite TODO list with new pending items"""
        kept_items = [
            item for item in self.todo_list
            if item.status in [TodoStatus.COMPLETED, TodoStatus.CANCELLED]
        ]
        
        new_items = []
        for content in items:
            new_items.append(TodoItem(
                id=self.next_todo_id,
                content=content,
                status=TodoStatus.PENDING
            ))
            self.next_todo_id += 1
        
        self.todo_list = kept_items + new_items
        
        return {
            "success": True,
            "kept_items": len(kept_items),
            "new_items": len(new_items),
            "total_items": len(self.todo_list)
        }
    
    def _tool_update_todo_status(self, updates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Update status of TODO items"""
        updated_count = 0
        
        for update in updates:
            item_id = update["id"]
            new_status = TodoStatus(update["status"])
            
            for item in self.todo_list:
                if item.id == item_id:
                    item.status = new_status
                    item.updated_at = datetime.now().isoformat()
                    updated_count += 1
                    break
        
        return {
            "success": True,
            "updated_items": updated_count,
            "total_items": len(self.todo_list)
        }
    
    def handle_event(self, event: Event, max_iterations: int = 20) -> Dict[str, Any]:
        """
        处理传入的事件并生成响应

        Args:
            event: 要处理的事件
            max_iterations: 工具调用的最大迭代次数

        Returns:
            包含 Agent 操作和最终答案的响应
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"📥 收到事件")
        logger.info(f"{'='*80}")
        logger.info(f"事件类型: {event.event_type.value}")
        logger.info(f"时间戳: {event.timestamp}")
        logger.info(f"内容: {event.content}")
        if event.metadata:
            logger.info(f"元数据: {json.dumps(event.metadata, indent=2)}")
        logger.info(f"{'='*80}\n")

        # 将事件转换为用户消息
        user_message = event.to_user_message()

        # 如果启用时间戳，添加时间戳前缀
        if self.config.enable_timestamps:
            timestamp_prefix = f"[{self._get_timestamp()}] "
            user_message = timestamp_prefix + user_message

        # 更新外部事件的上次用户交互时间
        if event.event_type in [EventType.WEB_MESSAGE, EventType.IM_MESSAGE, EventType.EMAIL_REPLY]:
            self.last_user_interaction = datetime.now()

        # 将用户消息添加到对话中
        self.conversation_history.append({"role": "user", "content": user_message})

        iteration = 0
        final_answer = None

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"迭代 {iteration}/{max_iterations}")

            self._advance_simulated_time(seconds=5)
            self._save_trajectory(iteration)
            
            try:
                messages_to_send = self.conversation_history.copy()
                system_hint = self._get_system_hint()
                if system_hint:
                    messages_to_send.append({"role": "user", "content": system_hint})
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages_to_send,
                    tools=self._get_tools_description(),
                    tool_choice="auto",
                    temperature=_reasoning_safe_temperature(self.model, self.config.temperature),
                    max_tokens=self.config.max_tokens
                )
                
                message = response.choices[0].message
                has_tool_calls = bool(getattr(message, "tool_calls", None))

                # 终止路径：没有工具调用的文本回复结束循环，
                # 即使没有 FINAL ANSWER: 标记（例如简单的 "hi" 回复）。
                # 以前只有 "FINAL ANSWER:" 会中断循环，所以简单的回复
                # 会被重新发送最多 max_iterations 次。
                if not has_tool_calls:
                    self.conversation_history.append(message.model_dump())
                    content = (message.content or "").strip()
                    if content:
                        final_answer = (content.split("FINAL ANSWER:", 1)[1].strip()
                                        if "FINAL ANSWER:" in content else content)
                        logger.info(f"✅ 终止文本响应（无工具调用）；最终答案: {final_answer[:100]}...")
                    else:
                        logger.warning("空模型响应且无工具调用；"
                                       "停止以避免消耗剩余迭代次数")
                    self._save_trajectory(iteration, final_answer)
                    break

                if has_tool_calls:
                    self.conversation_history.append(message.model_dump())

                    for tool_call in message.tool_calls:
                        function_name = tool_call.function.name
                        raw_args = tool_call.function.arguments or "{}"
                        try:
                            function_args = json.loads(raw_args)
                        except json.JSONDecodeError as exc:
                            # 格式错误/截断的参数不得中止当前轮次：
                            # 带有 tool_calls 的助手消息已经在历史中，因此
                            # 在此处中止会导致此 tool_call_id 未被回答，
                            # 并且每个后续请求都会被提供商拒绝。
                            err = (f"无效的工具参数（非有效 JSON）：{exc}。"
                                   f"原始参数: {raw_args[:500]}")
                            logger.warning(f"  ❌ {err}")
                            self.tool_calls.append(ToolCall(
                                tool_name=function_name, arguments={}, error=err))
                            self.conversation_history.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps({"error": err})
                            })
                            continue

                        if self.config.enable_tool_counter:
                            self.tool_call_counts[function_name] = self.tool_call_counts.get(function_name, 0) + 1
                            call_number = self.tool_call_counts[function_name]
                        else:
                            call_number = 1

                        logger.info(f"🔧 正在执行工具: {function_name}（第 {call_number} 次调用）")

                        args_str = json.dumps(function_args)
                        if len(args_str) > 200:
                            logger.info(f"  📥 参数: {args_str[:200]}...")
                        else:
                            logger.info(f"  📥 参数: {args_str}")

                        result, error = self._execute_tool(function_name, function_args)

                        if error:
                            error_preview = str(error).replace('\n', ' ')[:150]
                            logger.info(f"  ❌ 错误: {error_preview}")
                        else:
                            if isinstance(result, dict):
                                if result.get('success'):
                                    if 'output' in result and result['output']:
                                        output_preview = str(result['output']).replace('\n', ' ')[:100]
                                        logger.info(f"  ✅ 成功: {output_preview}...")
                                    elif 'content' in result:
                                        if result.get('partial_read'):
                                            logger.info(f"  ✅ 成功: 读取行 {result.get('begin_line', 1)}-{result.get('end_line', 0)} "
                                                      f"（{result.get('lines_read', 0)} 行）共 {result.get('total_lines', 0)} 行")
                                        else:
                                            logger.info(f"  ✅ 成功: 读取 {result.get('lines', 0)} 行，{result.get('size_bytes', 0)} 字节")
                                    elif 'file_path' in result:
                                        logger.info(f"  ✅ 成功: 对 {result['file_path']} 进行文件操作")
                                    else:
                                        logger.info(f"  ✅ 成功: 操作完成")
                                elif result.get('success') is False:
                                    if result.get('is_binary'):
                                        logger.info(f"  ⚠️  检测到二进制文件: {result.get('file_path', 'unknown')}")
                                    else:
                                        logger.info(f"  ⚠️  失败: {result.get('error', '未知错误')[:100]}")
                                else:
                                    logger.info(f"  ✅ 成功: 操作完成")
                            else:
                                result_preview = str(result).replace('\n', ' ')[:150]
                                logger.info(f"  ✅ 结果: {result_preview}")
                        
                        tool_call_record = ToolCall(
                            tool_name=function_name,
                            arguments=function_args,
                            result=result if not error else None,
                            error=error,
                            call_number=call_number
                        )
                        self.tool_calls.append(tool_call_record)
                        
                        tool_content = json.dumps(result)

                        metadata_parts = []
                        if self.config.enable_timestamps:
                            metadata_parts.append(f"[{self._get_timestamp()}]")
                        if self.config.enable_tool_counter:
                            metadata_parts.append(f"[对 '{function_name}' 的第 {call_number} 次工具调用]")

                        if metadata_parts:
                            tool_content = " ".join(metadata_parts) + "\n" + tool_content

                        self.conversation_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_content
                        })

                    # 如果同一轮次也标记了 FINAL ANSWER:（与工具调用一起
                    # 使用很少见），在记录工具结果后仍停止。
                    if message.content and "FINAL ANSWER:" in message.content:
                        final_answer = message.content.split("FINAL ANSWER:", 1)[1].strip()
                        logger.info(f"✅ 在工具调用旁找到最终答案: {final_answer[:100]}...")
                        self._save_trajectory(iteration, final_answer)
                        break

            except Exception as e:
                logger.error(f"事件处理期间出错: {str(e)}")
                self._save_trajectory(iteration)
                return {
                    "success": False,
                    "error": str(e),
                    "tool_calls": self.tool_calls,
                    "iterations": iteration,
                    "trajectory_file": self.config.trajectory_file if self.config.save_trajectory else None
                }

        self._save_trajectory(iteration, final_answer)

        logger.info(f"\n{'='*80}")
        logger.info(f"📤 Agent 响应")
        logger.info(f"{'='*80}")
        if final_answer:
            logger.info(f"响应: {final_answer}")
        else:
            logger.info(f"响应: 任务处理完成（{iteration} 次迭代）")
        logger.info(f"工具调用: {len(self.tool_calls)}")
        logger.info(f"{'='*80}\n")

        return {
            "final_answer": final_answer,
            "tool_calls": self.tool_calls,
            "todo_list": [
                {
                    "id": item.id,
                    "content": item.content,
                    "status": item.status.value
                }
                for item in self.todo_list
            ],
            "iterations": iteration,
            "success": final_answer is not None,
            "trajectory_file": self.config.trajectory_file if self.config.save_trajectory else None
        }

    def reset(self):
        """重置 Agent 的状态"""
        self.tool_call_counts = {}
        self.tool_calls = []
        self.todo_list = []
        self.next_todo_id = 1
        self.current_directory = os.getcwd()
        self.simulated_time = datetime.now()
        self.last_user_interaction = datetime.now()
        self.background_processes = {}
        self._init_system_prompt()
        logger.info("Agent 状态已重置")
    
    def __del__(self):
        """Cleanup when agent is destroyed"""
        if hasattr(self, 'mcp_manager') and self.mcp_manager.sessions:
            try:
                asyncio.run(self.mcp_manager.disconnect_all())
            except Exception as e:
                logger.warning(f"Error disconnecting MCP servers: {e}")
