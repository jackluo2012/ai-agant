"""
AI Agent 状态栏增强模块
===========================

本模块实现了 Agent 状态栏（Agent Status Bar）技术，通过在上下文末尾注入动态状态摘要
来改善 Agent 的执行轨迹管理，减少无限循环，提升上下文感知能力和任务管理效率。

核心功能：
- 时间戳跟踪：为消息添加时间前缀，帮助理解时序关系
- 工具调用计数器：记录工具调用次数，防止无限循环
- TODO 列表管理：任务进度跟踪和状态管理
- 详细错误信息：提供针对性的错误修复建议
- 系统状态感知：当前工作目录、系统信息等

作者：《AI Agent 开发实战》第2章 - 上下文工程
"""

import codecs
import json
import os
import sys
import subprocess
import platform
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from openai import OpenAI
import traceback


# 配置日志输出
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _reasoning_safe_temperature(model, requested=1.0):
    """
    推理模型温度设置安全检查

    推理模型（如 Kimi K3、GPT-5）只接受 temperature=1
    对于这些模型返回 1，其他模型返回请求的值

    Args:
        model: 模型名称
        requested: 请求的温度值

    Returns:
        适合该模型的温度值
    """
    m = str(model or "").lower().replace("/", "-")
    return 1 if ("kimi-k3" in m or "gpt-5" in m) else requested


class TodoStatus(Enum):
    """TODO 项目的状态枚举"""
    PENDING = "pending"           # 待处理
    IN_PROGRESS = "in_progress"   # 进行中
    COMPLETED = "completed"       # 已完成
    CANCELLED = "cancelled"       # 已取消


@dataclass
class TodoItem:
    """表示单个 TODO 项目"""
    id: int                           # 项目唯一标识符
    content: str                      # 项目内容描述
    status: TodoStatus = TodoStatus.PENDING  # 当前状态
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())  # 创建时间
    updated_at: Optional[str] = None  # 更新时间


@dataclass
class ToolCall:
    """表示单次工具调用及其增强跟踪信息"""
    tool_name: str                   # 工具名称
    arguments: Dict[str, Any]        # 调用参数
    result: Optional[Any] = None     # 执行结果
    error: Optional[str] = None      # 错误信息
    call_number: int = 1             # 该工具被调用的次数计数
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())  # 调用时间戳
    duration_ms: Optional[int] = None  # 执行耗时（毫秒）


@dataclass
class SystemHintConfig:
    """系统提示（状态栏）配置类"""
    enable_timestamps: bool = True           # 启用时间戳跟踪
    enable_tool_counter: bool = True          # 启用工具调用计数器
    enable_todo_list: bool = True             # 启用 TODO 列表管理
    enable_detailed_errors: bool = True       # 启用详细错误信息
    enable_system_state: bool = True          # 启用系统状态感知
    timestamp_format: str = "%Y-%m-%d %H:%M:%S"  # 时间戳格式
    simulate_time_delay: bool = False         # 模拟时间延迟（演示用）
    save_trajectory: bool = True              # 保存执行轨迹到文件
    trajectory_file: str = "trajectory.json"   # 轨迹文件路径


class StatusBarAgent:
    """
    带有系统提示增强的 AI Agent

    通过状态栏技术提供更好的轨迹管理、上下文感知和任务执行能力

    支持任意兼容 OpenAI API 格式的 LLM 提供商
    """

    def __init__(self, api_key: str, provider: str = "kimi",
                 model: Optional[str] = None, base_url: Optional[str] = None,
                 config: Optional[SystemHintConfig] = None,
                 verbose: bool = True):
        """
        初始化 Agent

        Args:
            api_key: LLM 提供商的 API 密钥
            provider: LLM 提供商标识
                - 预设: 'kimi', 'moonshot', 'openai', 'deepseek', 'anthropic'
                - 或使用 'custom' 配合自定义 base_url
            model: 模型名称（如不指定，使用提供商默认模型）
            base_url: API 基础 URL（可选，用于自定义提供商）
            config: 系统提示配置
            verbose: 如果为 True，记录详细信息
        """
        self.provider = provider.lower()
        self.verbose = verbose
        self.config = config or SystemHintConfig()

        # 预设提供商配置
        provider_configs = {
            'kimi': {'base_url': 'https://api.moonshot.cn/v1', 'default_model': 'kimi-k3'},
            'moonshot': {'base_url': 'https://api.moonshot.cn/v1', 'default_model': 'kimi-k3'},
            'openai': {'base_url': 'https://api.openai.com/v1', 'default_model': 'gpt-4o'},
            'deepseek': {'base_url': 'https://api.deepseek.com', 'default_model': 'deepseek-chat'},
            'anthropic': {'base_url': 'https://api.anthropic.com/v1', 'default_model': 'claude-sonnet-4-20250514'},
            'azure': {'base_url': None, 'default_model': None},  # Azure 需要完整 base_url
        }

        # 解析配置
        if self.provider in provider_configs:
            config_data = provider_configs[self.provider]
            resolved_base_url = base_url or config_data['base_url']
            default_model = config_data['default_model']
        else:
            # 自定义提供商
            resolved_base_url = base_url
            default_model = None
            logger.info(f"使用自定义提供商配置: base_url={base_url}")

        # 验证必需参数
        if not resolved_base_url:
            raise ValueError(f"提供商 '{provider}' 需要提供 base_url 参数")

        # 创建 OpenAI 客户端
        self.client = OpenAI(api_key=api_key, base_url=resolved_base_url)
        self.model = model or default_model

        if not self.model:
            raise ValueError(f"请提供 model 参数（提供商: {provider}）")

        logger.info(f"状态栏 Agent 已初始化 - 提供商: {self.provider}, 模型: {self.model}, API: {resolved_base_url}")

        # 初始化跟踪变量
        self.tool_call_counts: Dict[str, int] = {}  # 工具调用计数
        self.tool_calls: List[ToolCall] = []         # 工具调用历史
        self.todo_list: List[TodoItem] = []          # TODO 列表
        self.next_todo_id = 1                        # 下一个 TODO ID

        # 初始化对话历史
        self.conversation_history = []
        self.simulated_time = datetime.now()  # 用于演示的时间模拟

        # 初始化系统提示词
        self._init_system_prompt()

        # 跟踪当前工作目录
        self.current_directory = os.getcwd()

        # 跟踪发送给 LLM 的最后消息
        self.last_llm_messages = None

        logger.info(f"状态栏 Agent 已初始化 - 提供商: {self.provider}, 模型: {self.model}")

    def _init_system_prompt(self):
        """初始化对话的系统提示词"""
        system_content = """你是一个智能助手，可以使用各种工具完成文件操作、代码执行和系统命令。

你的任务是高效地使用可用工具来完成给定的目标。请一步步思考，按需使用工具。

## TODO 列表管理规则：
- 对于任何包含 3 个以上步骤的复杂任务，立即使用 `rewrite_todo_list` 创建 TODO 列表
- 将用户的请求分解为具体、可操作的 TODO 项目
- 开始工作时使用 `update_todo_status` 将 TODO 项目更新为 'in_progress'
- 完成后立即将项目标记为 'completed'
- 同时只能有一个项目处于 'in_progress' 状态
- 如果遇到错误或需要改变方法，将相关 TODO 更新为 'cancelled' 并添加新项目
- 使用 TODO 列表作为你的主要规划和跟踪机制
- 讨论进度时引用 TODO 项目的 ID

## 关键行为准则：
1. 复杂任务总是从创建 TODO 列表开始
2. 注意时间戳以理解事件的时间线
3. 注意工具调用编号（如 "Tool call #3"）以避免重复循环 - 如果看到高编号，改变策略
4. 从详细错误信息中学习以修复问题并调整方法
5. 注意系统状态中显示的当前目录和系统环境
6. 探索项目时，系统地阅读关键文件（README、main.py、agent.py）以理解结构

## 错误处理：
- 仔细阅读错误消息 - 它们包含关于出错的具体信息
- 使用错误消息中提供的建议来修复问题
- 如果工具多次失败（检查调用编号），尝试不同的方法
- 常见修复方法：检查文件路径、验证当前目录、确保适当的权限

重要提示：完成所有任务后，清楚地说明 "FINAL ANSWER:" 后跟对所完成工作的全面总结。"""

        self.conversation_history = [
            {"role": "system", "content": system_content}
        ]

    def _get_system_state(self) -> str:
        """获取当前系统状态信息"""
        if not self.config.enable_system_state:
            return ""

        # 检测操作系统类型
        system = platform.system()
        if system == "Windows":
            shell_type = "Windows 命令提示符或 PowerShell"
        elif system == "Darwin":
            shell_type = "macOS 终端 (zsh/bash)"
        else:
            shell_type = f"Linux Shell ({os.environ.get('SHELL', 'bash')})"

        state_info = [
            f"当前时间: {self._get_timestamp()}",
            f"当前目录: {self.current_directory}",
            f"系统: {system} ({platform.release()})",
            f"Shell 环境: {shell_type}",
            f"Python 版本: {sys.version.split()[0]}"
        ]

        return "\n".join(state_info)

    def _get_timestamp(self) -> str:
        """获取格式化的时间戳"""
        if self.config.simulate_time_delay:
            # 演示模式：使用模拟时间
            return self.simulated_time.strftime(self.config.timestamp_format)
        return datetime.now().strftime(self.config.timestamp_format)

    def _advance_simulated_time(self, hours: int = 0, minutes: int = 0, seconds: int = 30):
        """推进模拟时间（用于演示）"""
        if self.config.simulate_time_delay:
            self.simulated_time += timedelta(hours=hours, minutes=minutes, seconds=seconds)

    def _save_trajectory(self, iteration: int, final_answer: Optional[str] = None):
        """
        保存当前执行轨迹到 JSON 文件以便调试

        Args:
            iteration: 当前迭代次数
            final_answer: 最终答案（可选）
        """
        if not self.config.save_trajectory:
            return

        trajectory_data = {
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "provider": self.provider,
            "model": self.model,
            "conversation_history": self.conversation_history,
            "last_llm_messages": self.last_llm_messages,
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
            # 保存到文件，每次覆盖以捕获最新状态
            with open(self.config.trajectory_file, 'w', encoding='utf-8') as f:
                json.dump(trajectory_data, f, indent=2, ensure_ascii=False)

            if self.verbose:
                logger.info(f"轨迹已保存到 {self.config.trajectory_file} (迭代 {iteration})")
        except Exception as e:
            logger.warning(f"保存轨迹失败: {e}")

    def _format_todo_list(self) -> str:
        """格式化 TODO 列表以供显示"""
        if not self.todo_list:
            return "TODO 列表: 空"

        lines = ["TODO 列表:"]
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
        """
        获取包含当前状态的系统提示内容

        这个方法实现了 Agent 状态栏的核心功能：
        将分散的隐式状态提炼为显式知识，以最小的 token 成本
        呈现出原本需要扫描数千个 token 才能获得的信息。
        """
        if not any([self.config.enable_system_state, self.config.enable_todo_list]):
            return None

        hint_parts = []

        if self.config.enable_system_state:
            hint_parts.append("=== 系统状态 ===")
            hint_parts.append(self._get_system_state())
            hint_parts.append("")

        if self.config.enable_todo_list and self.todo_list:
            hint_parts.append("=== 当前任务 ===")
            hint_parts.append(self._format_todo_list())
            hint_parts.append("")

        if hint_parts:
            return "\n".join(hint_parts)
        return None

    def _get_tools_description(self) -> List[Dict[str, Any]]:
        """获取模型的工具描述"""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "读取文本文件内容。二进制文件返回错误。支持大文件的部分读取。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "要读取的文件路径（绝对路径或相对于当前目录的相对路径）"
                            },
                            "begin_line": {
                                "type": "integer",
                                "description": "可选：开始读取的行号（从1开始索引）。例如 begin_line=10 从第10行开始读取。"
                            },
                            "number_lines": {
                                "type": "integer",
                                "description": "可选：从 begin_line 开始读取的行数。例如 number_lines=50 读取 50 行。"
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
                    "description": "将内容写入文件（创建或覆盖）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "要写入的文件路径"
                            },
                            "content": {
                                "type": "string",
                                "description": "要写入文件的内容"
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
                    "description": "在受限环境中执行 Python 代码",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "要执行的 Python 代码"
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
                    "description": "在当前目录中执行 Shell 命令",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "要执行的 Shell 命令"
                            },
                            "working_dir": {
                                "type": "string",
                                "description": "可选的工作目录（默认为当前目录）"
                            }
                        },
                        "required": ["command"]
                    }
                }
            }
        ]

        # 如果启用，添加 TODO 管理工具
        if self.config.enable_todo_list:
            tools.extend([
                {
                    "type": "function",
                    "function": {
                        "name": "rewrite_todo_list",
                        "description": "使用新的待处理项目重写 TODO 列表（保留已完成/已取消的项目）",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "items": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "要添加为待处理的新 TODO 项目列表"
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
                        "description": "更新现有 TODO 项目的状态",
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
                                                "description": "TODO 项目 ID"
                                            },
                                            "status": {
                                                "type": "string",
                                                "enum": ["pending", "in_progress", "completed", "cancelled"],
                                                "description": "项目的新状态"
                                            }
                                        },
                                        "required": ["id", "status"]
                                    },
                                    "description": "要更新的 TODO 项目列表及其新状态"
                                }
                            },
                            "required": ["updates"]
                        }
                    }
                }
            ])

        return tools

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[Any, Optional[str], Optional[int]]:
        """
        执行工具并返回带有详细错误信息的结果

        Returns:
            (结果, 错误详情, 耗时毫秒) 元组
        """
        start_time = datetime.now()

        try:
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
                error = f"未知工具: {tool_name}"
                return {"error": error}, error, None

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return result, None, duration_ms

        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # 获取详细错误信息
            error_detail = self._get_detailed_error(e, tool_name, arguments)

            if self.config.enable_detailed_errors:
                return {"error": error_detail}, error_detail, duration_ms
            else:
                return {"error": str(e)}, str(e), duration_ms

    def _get_detailed_error(self, exception: Exception, tool_name: str, arguments: Dict[str, Any]) -> str:
        """获取用于调试的详细错误信息"""
        error_parts = [
            f"工具 '{tool_name}' 执行失败，错误类型: {type(exception).__name__}, 错误信息: {str(exception)}",
            f"调用参数: {json.dumps(arguments, indent=2, ensure_ascii=False)}",
        ]

        # 添加调试用的堆栈跟踪
        if self.verbose:
            tb = traceback.format_exc()
            error_parts.append(f"堆栈跟踪:\n{tb}")

        # 根据错误类型添加建议
        suggestions = self._get_error_suggestions(exception, tool_name)
        if suggestions:
            error_parts.append(f"修复建议: {suggestions}")

        return "\n".join(error_parts)

    def _get_error_suggestions(self, exception: Exception, tool_name: str) -> str:
        """获取针对常见错误的修复建议"""
        error_str = str(exception).lower()
        exception_type = type(exception).__name__

        suggestions = []

        if "permission" in error_str or exception_type == "PermissionError":
            suggestions.append("检查文件/目录权限")
            suggestions.append("尝试使用不同的目录或以适当的权限运行")
        elif "not found" in error_str or "no such file" in error_str or exception_type == "FileNotFoundError":
            suggestions.append("验证文件/目录路径是否存在")
            suggestions.append("检查当前工作目录")
            suggestions.append("使用绝对路径或先创建文件/目录")
        elif "syntax" in error_str or exception_type == "SyntaxError":
            suggestions.append("检查代码语法")
            suggestions.append("确保正确的缩进和有效的 Python 语法")
        elif "timeout" in error_str:
            suggestions.append("操作耗时太长")
            suggestions.append("尝试使用更简单的输入或分解为更小的步骤")
        elif "import" in error_str or exception_type == "ImportError":
            suggestions.append("受限环境中不可用所需模块")
            suggestions.append("仅使用内置 Python 模块")

        return " | ".join(suggestions) if suggestions else ""

    # ===== 工具实现 =====

    def _tool_read_file(self, file_path: str, begin_line: Optional[int] = None,
                       number_lines: Optional[int] = None) -> Dict[str, Any]:
        """读取文件内容，支持基于行的部分读取"""
        try:
            # 解析相对于当前目录的路径
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.current_directory, file_path)

            # 检查文件是否存在
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件未找到: {file_path}")

            # 检查是否为二进制文件
            try:
                with open(file_path, 'rb') as f:
                    # 读取前 1024 字节检查二进制内容
                    chunk = f.read(1024)
                    # 检查空字节（二进制文件的常见特征）
                    if b'\x00' in chunk:
                        return {
                            "success": False,
                            "error": "无法读取二进制文件。此工具仅支持文本文件。",
                            "file_path": file_path,
                            "is_binary": True
                        }
                    # 同时检查是否为有效的 UTF-8。使用增量解码器，
                    # 设置 final=False，这样多字节字符被 1024 字节读取边界分割时
                    # 不会被误认为是二进制内容（每个 CJK 字符都是 3 字节，这很常见）。
                    try:
                        codecs.getincrementaldecoder('utf-8')().decode(chunk, False)
                    except UnicodeDecodeError:
                        return {
                            "success": False,
                            "error": "文件不是有效的文本文件（编码错误）。",
                            "file_path": file_path,
                            "is_binary": True
                        }
            except Exception as e:
                # 如果无法作为二进制读取，可能是权限问题
                raise

            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                if begin_line is not None or number_lines is not None:
                    # 基于行的读取
                    all_lines = f.readlines()
                    total_lines = len(all_lines)

                    # 计算行范围
                    start_line = (begin_line - 1) if begin_line is not None else 0
                    if start_line < 0:
                        start_line = 0
                    if start_line >= total_lines:
                        return {
                            "success": False,
                            "error": f"begin_line {begin_line} 超出了文件长度（{total_lines} 行）",
                            "file_path": file_path,
                            "total_lines": total_lines
                        }

                    if number_lines is not None:
                        end_line = min(start_line + number_lines, total_lines)
                    else:
                        end_line = total_lines

                    # 获取请求的行
                    selected_lines = all_lines[start_line:end_line]
                    content = ''.join(selected_lines)

                    # 获取文件信息
                    stat = os.stat(file_path)

                    return {
                        "success": True,
                        "file_path": file_path,
                        "content": content,
                        "size_bytes": stat.st_size,
                        "total_lines": total_lines,
                        "begin_line": start_line + 1,  # 转换回从1开始
                        "end_line": end_line,
                        "lines_read": len(selected_lines),
                        "partial_read": True
                    }
                else:
                    # 完整文件读取
                    content = f.read()

                    # 获取文件信息
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
        """将内容写入文件"""
        try:
            # 解析相对于当前目录的路径
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.current_directory, file_path)

            # 如有必要，创建目录
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
        """在受限环境中执行 Python 代码"""
        try:
            import io
            import contextlib

            output_buffer = io.StringIO()
            error_buffer = io.StringIO()

            # 使用显式命名空间运行：使用裸 exec(code) 时，
            # 顶层赋值会落在这个方法的 locals 中，而代码片段中定义的函数
            # 通过模块全局变量解析自由变量，所以
            # "x = 5; def f(): return x; f()" 会引发 NameError。
            exec_ns = {}
            with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
                exec(code, exec_ns)

            # 获取输出
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
        """执行 Shell 命令"""
        try:
            # 如果未指定，使用当前目录
            if working_dir is None:
                working_dir = self.current_directory
            elif not os.path.isabs(working_dir):
                working_dir = os.path.join(self.current_directory, working_dir)

            # 如果命令是纯 'cd'，更新当前目录
            # 复合命令如 `cd proj && make` 必须传递给下面的 subprocess
            # （使用 cwd=working_dir 运行）—— 在这里拦截它们会将
            # "proj && make" 视为目录名称并因"目录未找到"而失败。
            stripped = command.strip()
            if stripped.startswith('cd ') and not any(t in stripped for t in ('&&', ';', '|')):
                new_dir = stripped[3:].strip()
                if not os.path.isabs(new_dir):
                    new_dir = os.path.join(self.current_directory, new_dir)

                if os.path.isdir(new_dir):
                    self.current_directory = os.path.abspath(new_dir)
                    return {
                        "success": True,
                        "command": command,
                        "output": f"已更改目录到: {self.current_directory}",
                        "return_code": 0
                    }
                else:
                    raise FileNotFoundError(f"目录未找到: {new_dir}")

            # 执行命令
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
            raise TimeoutError(f"命令超时（30秒）: {command}")
        except Exception as e:
            raise

    def _tool_rewrite_todo_list(self, items: List[str]) -> Dict[str, Any]:
        """使用新的待处理项目重写 TODO 列表"""
        # 保留已完成和已取消的项目
        kept_items = [
            item for item in self.todo_list
            if item.status in [TodoStatus.COMPLETED, TodoStatus.CANCELLED]
        ]

        # 创建新的待处理项目
        new_items = []
        for content in items:
            new_items.append(TodoItem(
                id=self.next_todo_id,
                content=content,
                status=TodoStatus.PENDING
            ))
            self.next_todo_id += 1

        # 更新 TODO 列表
        self.todo_list = kept_items + new_items

        return {
            "success": True,
            "kept_items": len(kept_items),
            "new_items": len(new_items),
            "total_items": len(self.todo_list)
        }

    def _tool_update_todo_status(self, updates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """更新 TODO 项目的状态"""
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

    def execute_task(self, task: str, max_iterations: int = 20) -> Dict[str, Any]:
        """
        使用可用工具和系统提示执行任务

        Args:
            task: 要执行的任务
            max_iterations: 最大工具调用次数

        Returns:
            任务执行结果
        """
        # 如果启用，为用户消息添加时间戳
        if self.config.enable_timestamps:
            timestamp_prefix = f"[{self._get_timestamp()}] "
            task = timestamp_prefix + task

        # 添加用户消息
        self.conversation_history.append({"role": "user", "content": task})

        iteration = 0
        final_answer = None

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"迭代 {iteration}/{max_iterations}")

            # 演示用的模拟时间推进
            self._advance_simulated_time(seconds=5)

            # 在每次迭代开始时保存轨迹
            self._save_trajectory(iteration)

            try:
                # 准备发送给模型的消息 - 添加系统提示作为最后一条用户消息
                messages_to_send = self.conversation_history.copy()
                system_hint = self._get_system_hint()
                if system_hint:
                    messages_to_send.append({"role": "user", "content": system_hint})

                # 存储发送给 LLM 的消息以便轨迹记录
                self.last_llm_messages = messages_to_send

                # 调用模型
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages_to_send,
                    tools=self._get_tools_description(),
                    tool_choice="auto",
                    temperature=_reasoning_safe_temperature(self.model, 0.3),
                    max_tokens=8192
                )

                message = response.choices[0].message
                has_tool_calls = bool(getattr(message, "tool_calls", None))

                # 终止路径：没有工具调用的文本回复结束循环，
                # 即使没有 FINAL ANSWER: 标记（例如简单的 "hi" 回复）。
                # 以前只有 "FINAL ANSWER:" 才会中断循环，
                # 所以简单回复会被重新发送最多 max_iterations 次。
                if not has_tool_calls:
                    self.conversation_history.append(message.model_dump())
                    content = (message.content or "").strip()
                    if content:
                        final_answer = (content.split("FINAL ANSWER:", 1)[1].strip()
                                        if "FINAL ANSWER:" in content else content)
                        logger.info(f"终端文本响应（无工具调用）；最终答案: {final_answer[:100]}...")
                    else:
                        logger.warning("空的模型响应且无工具调用；"
                                       "停止以避免消耗剩余迭代次数")
                    # 保存最终轨迹
                    self._save_trajectory(iteration, final_answer)
                    break

                # 处理工具调用
                if has_tool_calls:
                    self.conversation_history.append(message.model_dump())

                    for tool_call in message.tool_calls:
                        function_name = tool_call.function.name
                        raw_args = tool_call.function.arguments or "{}"
                        try:
                            function_args = json.loads(raw_args)
                        except json.JSONDecodeError as exc:
                            # 在错误的工具参数 JSON 上保持回合活跃
                            err = (
                                f"无效的工具参数（不是有效的 JSON）: {exc}. "
                                f"原始参数: {raw_args[:500]}"
                            )
                            logger.warning(f"  ❌ {err}")
                            self.tool_calls.append(ToolCall(
                                tool_name=function_name,
                                arguments={},
                                error=err,
                            ))
                            self.conversation_history.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps({"error": err}),
                            })
                            continue

                        # 跟踪工具调用计数
                        if self.config.enable_tool_counter:
                            self.tool_call_counts[function_name] = self.tool_call_counts.get(function_name, 0) + 1
                            call_number = self.tool_call_counts[function_name]
                        else:
                            call_number = 1

                        logger.info(f"执行工具: {function_name} (调用 #{call_number})")

                        # 打印工具参数（简洁格式）
                        args_str = json.dumps(function_args, ensure_ascii=False)
                        if len(args_str) > 200:
                            logger.info(f"  📥 参数: {args_str[:200]}...")
                        else:
                            logger.info(f"  📥 参数: {args_str}")

                        # 执行工具
                        result, error, duration_ms = self._execute_tool(function_name, function_args)

                        # 打印工具结果（简洁格式）
                        if error:
                            error_preview = str(error).replace('\n', ' ')[:150]
                            logger.info(f"  ❌ 错误: {error_preview}")
                        else:
                            if isinstance(result, dict):
                                if result.get('success'):
                                    # 显示成功操作的关键信息
                                    if 'output' in result and result['output']:
                                        output_preview = str(result['output']).replace('\n', ' ')[:100]
                                        logger.info(f"  ✅ 成功: {output_preview}...")
                                    elif 'content' in result:
                                        # 处理 read_file 结果
                                        if result.get('partial_read'):
                                            logger.info(f"  ✅ 成功: 读取行 {result.get('begin_line', 1)}-{result.get('end_line', 0)} "
                                                      f"({result.get('lines_read', 0)} 行) / 共 {result.get('total_lines', 0)} 行")
                                        else:
                                            logger.info(f"  ✅ 成功: 读取 {result.get('lines', 0)} 行, {result.get('size_bytes', 0)} 字节")
                                    elif 'file_path' in result:
                                        logger.info(f"  ✅ 成功: 文件操作 {result['file_path']}")
                                    else:
                                        logger.info(f"  ✅ 成功: 操作已完成")
                                elif result.get('success') is False:
                                    # 处理显式失败（如二进制文件检测）
                                    if result.get('is_binary'):
                                        logger.info(f"  ⚠️ 检测到二进制文件: {result.get('file_path', 'unknown')}")
                                    else:
                                        logger.info(f"  ⚠️ 失败: {result.get('error', '未知错误')[:100]}")
                                else:
                                    logger.info(f"  ✅ 成功: 操作已完成")
                            else:
                                result_preview = str(result).replace('\n', ' ')[:150]
                                logger.info(f"  ✅ 结果: {result_preview}")

                        # 记录工具调用
                        tool_call_record = ToolCall(
                            tool_name=function_name,
                            arguments=function_args,
                            result=result if not error else None,
                            error=error,
                            call_number=call_number,
                            duration_ms=duration_ms
                        )
                        self.tool_calls.append(tool_call_record)

                        # 准备工具结果消息
                        tool_content = json.dumps(result, ensure_ascii=False)

                        # 如果启用，添加元数据到工具结果
                        metadata_parts = []

                        if self.config.enable_timestamps:
                            metadata_parts.append(f"[{self._get_timestamp()}]")

                        if self.config.enable_tool_counter:
                            metadata_parts.append(f"[工具调用 #{call_number} 用于 '{function_name}']")

                        if metadata_parts:
                            tool_content = " ".join(metadata_parts) + "\n" + tool_content

                        # 添加工具结果
                        self.conversation_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_content
                        })

                    # 如果同一回合也标记了 FINAL ANSWER:（与工具调用一起时很少见），
                    # 仍然在记录工具结果后停止。
                    if message.content and "FINAL ANSWER:" in message.content:
                        final_answer = message.content.split("FINAL ANSWER:", 1)[1].strip()
                        logger.info(f"与工具调用一起找到最终答案: {final_answer[:100]}...")
                        self._save_trajectory(iteration, final_answer)
                        break

            except Exception as e:
                logger.error(f"任务执行期间出错: {str(e)}")
                # 即使出错也保存轨迹
                self._save_trajectory(iteration)
                return {
                    "error": str(e),
                    "tool_calls": self.tool_calls,
                    "iterations": iteration,
                    "trajectory_file": self.config.trajectory_file if self.config.save_trajectory else None
                }

        # 在返回前保存最终轨迹
        self._save_trajectory(iteration, final_answer)

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
        self.last_llm_messages = None
        self._init_system_prompt()
        logger.info("Agent 状态已重置")
