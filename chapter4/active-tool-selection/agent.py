"""
主动工具发现代理 (Active Tool Discovery Agent)

实现一个 LLM 代理，它按需主动请求工具，而不是预先将所有工具模式注入提示词。
受 MCP-Zero 启发。
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

from typing import List, Dict, Any, Optional

try:
    from llm.client import get_llm_client
except ImportError:
    get_llm_client = None

from tool_knowledge_base import ToolDefinition, ServerDefinition, create_tool_knowledge_base
from semantic_router import SemanticRouter, StructuredRequestParser
import config


class ActiveToolAgent:
    """
    主动发现和请求工具的代理。

    核心原则:
    1. 通过不预先注入所有工具来维持最小上下文
    2. 当识别到能力缺口时主动请求特定工具
    3. 随着任务理解的发展迭代构建工具链
    """

    def __init__(self, servers: Optional[List[ServerDefinition]] = None,
                 model: Optional[str] = None):
        # 获取统一 LLM 客户端
        if get_llm_client is not None:
            self.client = get_llm_client()
            self.model = self.client.model_name
        else:
            raise ImportError("无法导入 llm.client，请确保项目根目录的 .env 文件配置正确")

        # 覆盖模型（如果提供）
        if model:
            self.model = model

        # 初始化工具知识库（调用者可以注入自定义目录）
        self.servers = servers if servers is not None else create_tool_knowledge_base()
        self.router = SemanticRouter(self.servers)

        # 代理状态
        self.conversation_history = []
        self.available_tools: List[ToolDefinition] = []  # 当前已加载的工具
        self.tool_request_count = 0

        # 指标
        self.metrics = {
            'tokens_used': 0,
            'tool_requests': 0,
            'tools_loaded': 0,
            'api_calls': 0,
            'tools_called': []  # 模型实际调用的工具名称
        }

    def execute_task(self, task: str) -> Dict[str, Any]:
        """
        使用主动工具发现执行任务。

        代理将:
        1. 分析任务
        2. 识别能力缺口
        3. 请求特定工具
        4. 使用发现的工具执行

        返回包含指标的执行结果。
        """
        self.conversation_history = []
        self.available_tools = []
        self.tool_request_count = 0

        # 初始系统消息，解释主动工具发现
        system_message = self._create_system_message()
        self.conversation_history.append({
            "role": "system",
            "content": system_message
        })

        # 添加用户任务
        self.conversation_history.append({
            "role": "user",
            "content": task
        })

        # 迭代工具发现和执行
        max_iterations = config.MAX_TOOL_REQUESTS
        for iteration in range(max_iterations):
            # 获取代理响应
            response = self._call_llm()
            self.metrics['api_calls'] += 1

            # 检查代理是否正在请求工具
            tool_request = StructuredRequestParser.parse_request(response)

            if tool_request:
                # 代理正在请求工具 - 发现并提供它们
                self._handle_tool_request(tool_request, response)
                self.tool_request_count += 1
                self.metrics['tool_requests'] += 1
            else:
                # 代理已有所需资源并正在响应
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response
                })
                break

        return {
            'response': response,
            'metrics': self.metrics,
            'tools_loaded': [t.name for t in self.available_tools],
            'conversation': self.conversation_history
        }

    def _create_system_message(self) -> str:
        """创建解释主动工具发现的系统消息。"""
        return """你是一个具有主动工具发现能力的自主 AI 代理。

你不需要在开始时拥有所有可能的工具，而是可以根据需要主动请求工具。这让你能够:
1. 维持最小的上下文占用
2. 专注于与当前任务相关的能力
3. 随着理解的发展迭代构建工具链

当你识别到能力缺口时，使用以下格式请求工具:

<tool_request>
server: [描述你需要的平台/域，例如 "GitHub 用于代码仓库操作" 或 "文件系统用于本地文件访问"]
tool: [描述你需要的具体操作，例如 "搜索仓库" 或 "读取文件内容"]
</tool_request>

请求工具后，它们将被提供给你。然后你可以使用它们完成任务。

流程:
1. 分析任务并识别你需要什么能力
2. 如果还没有工具，请求特定工具
3. 拥有必要的工具后，使用它们完成任务
4. 用你的发现或结果响应

当前可用工具: 无（按需请求工具）"""

    def _call_llm(self) -> str:
        """使用当前上下文和可用工具调用 LLM。"""
        kwargs = {
            "model": self.model,
            "messages": self.conversation_history,
            "temperature": config.AGENT_TEMPERATURE
        }

        # 如果有可用工具，添加它们
        if self.available_tools:
            kwargs["tools"] = [tool.to_schema() for tool in self.available_tools]
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)

        # 跟踪 token 使用
        # response.usage 在 OpenAI SDK 中是 Optional: 属性始终存在
        # 但当提供者省略 token 计数时为 None
        if getattr(response, 'usage', None):
            self.metrics['tokens_used'] += response.usage.total_tokens

        # 提取响应内容
        message = response.choices[0].message

        # 处理工具调用（如果存在）
        if message.tool_calls:
            return self._handle_tool_calls(message)

        return message.content or ""

    def _handle_tool_request(self, tool_request: Dict[str, str], full_response: str):
        """
        处理来自代理的工具请求。

        Args:
            tool_request: 解析的工具请求，包含 'server' 和 'tool' 字段
            full_response: 来自代理的完整响应文本
        """
        # 结合服务器和工具描述进行路由
        query = f"{tool_request['server']} {tool_request['tool']}"

        # 使用语义路由器查找相关工具
        discovered_tools = self.router.route_request(query)

        if not discovered_tools:
            # 未找到工具
            feedback = f"""未找到匹配你请求的工具。请优化你的请求或在没有额外工具的情况下继续。

你的请求是:
- 服务器: {tool_request['server']}
- 工具: {tool_request['tool']}"""
        else:
            # 将发现的工具添加到可用工具
            new_tools = []
            for tool in discovered_tools:
                if tool not in self.available_tools:
                    self.available_tools.append(tool)
                    new_tools.append(tool)
                    self.metrics['tools_loaded'] += 1

            tool_list = "\n".join([f"- {t.name}: {t.description}" for t in new_tools])
            feedback = f"""发现并加载了 {len(new_tools)} 个新工具：

{tool_list}

你现在可以使用这些工具完成任务。请继续。"""

        # 将代理的请求和系统的响应添加到历史
        self.conversation_history.append({
            "role": "assistant",
            "content": full_response
        })
        self.conversation_history.append({
            "role": "user",
            "content": feedback
        })

    def _handle_tool_calls(self, message) -> str:
        """处理实际工具执行（本演示为模拟）。"""
        # 对于本教育演示，我们模拟工具执行
        tool_results = []

        for tool_call in message.tool_calls:
            func_name = tool_call.function.name
            self.metrics['tools_called'].append(func_name)

            # 模拟工具执行
            result = f"[模拟] 工具 '{func_name}' 成功执行，结果: 成功"
            tool_results.append({
                "tool_call_id": tool_call.id,
                "output": result
            })

        # 将工具调用消息添加到历史
        self.conversation_history.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
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
        })

        # 将工具结果添加到历史
        for result in tool_results:
            self.conversation_history.append({
                "role": "tool",
                "tool_call_id": result["tool_call_id"],
                "content": result["output"]
            })

        # 获取工具执行后的最终响应
        return self._call_llm()

    def reset(self):
        """重置代理状态。"""
        self.conversation_history = []
        self.available_tools = []
        self.tool_request_count = 0
        self.metrics = {
            'tokens_used': 0,
            'tool_requests': 0,
            'tools_loaded': 0,
            'api_calls': 0,
            'tools_called': []
        }


class RetrievalToolAgent:
    """
    单次检索代理（语义工具检索 / "工具检索"）。

    这是被动注入和主动发现之间的 RAG 风折中方案：在第一次 LLM 调用之前，
    它检索与任务最相关的 top-k 工具并仅注入这些工具。没有额外的发现往返 ——
    工具选择委托给检索器，将"数百个工具中选择哪个"问题转化为知识检索问题。

    这直接体现了章节归因于 Anthropic 按需工具检索实验的机制：
    更少、更相关的工具模式既降低 token 成本又减少模型的选择错误。
    """

    def __init__(self, servers: Optional[List[ServerDefinition]] = None,
                 model: Optional[str] = None, top_k: Optional[int] = None):
        # 获取统一 LLM 客户端
        if get_llm_client is not None:
            self.client = get_llm_client()
            self.model = self.client.model_name
        else:
            raise ImportError("无法导入 llm.client，请确保项目根目录的 .env 文件配置正确")

        # 覆盖模型（如果提供）
        if model:
            self.model = model

        self.top_k = top_k if top_k is not None else config.TOP_K_TOOLS

        self.servers = servers if servers is not None else create_tool_knowledge_base()
        self.router = SemanticRouter(self.servers)

        self.conversation_history = []
        self.available_tools: List[ToolDefinition] = []
        self.metrics = {
            'tokens_used': 0,
            'tools_loaded': 0,
            'api_calls': 0,
            'tools_called': []
        }

    def execute_task(self, task: str) -> Dict[str, Any]:
        """检索任务的 top-k 相关工具，然后一次性执行。"""
        self.conversation_history = []

        # 检索步骤（无 LLM 调用）：选择 top-k 最相关工具
        self.available_tools = self.router.retrieve(task, self.top_k)
        self.metrics['tools_loaded'] = len(self.available_tools)

        tool_list = "\n".join(
            f"- {t.name}: {t.description}" for t in self.available_tools
        )
        system_message = f"""你是一个 AI 代理。检索系统预选择了以下 {len(self.available_tools)} 个工具，认为它们与用户的任务最相关。

{tool_list}

分析任务并调用适当的工具来完成它。"""

        self.conversation_history.append({"role": "system", "content": system_message})
        self.conversation_history.append({"role": "user", "content": task})

        response = self._call_llm()
        self.metrics['api_calls'] += 1

        return {
            'response': response,
            'metrics': self.metrics,
            'tools_loaded': [t.name for t in self.available_tools],
            'conversation': self.conversation_history
        }

    def _call_llm(self) -> str:
        """仅使用检索到的工具调用 LLM。"""
        kwargs = {
            "model": self.model,
            "messages": self.conversation_history,
            "temperature": config.AGENT_TEMPERATURE
        }
        if self.available_tools:
            kwargs["tools"] = [tool.to_schema() for tool in self.available_tools]
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)

        # response.usage 在 OpenAI SDK 中是 Optional: 属性始终存在
        # 但当提供者省略 token 计数时为 None
        if getattr(response, 'usage', None):
            self.metrics['tokens_used'] += response.usage.total_tokens

        message = response.choices[0].message
        if message.tool_calls:
            return self._handle_tool_calls(message)
        return message.content or ""

    def _handle_tool_calls(self, message) -> str:
        """处理工具执行（模拟）。"""
        tool_results = []
        for tool_call in message.tool_calls:
            func_name = tool_call.function.name
            self.metrics['tools_called'].append(func_name)
            result = f"[模拟] 工具 '{func_name}' 成功执行"
            tool_results.append({"tool_call_id": tool_call.id, "output": result})

        self.conversation_history.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
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
        })
        for result in tool_results:
            self.conversation_history.append({
                "role": "tool",
                "tool_call_id": result["tool_call_id"],
                "content": result["output"]
            })
        return self._call_llm()

    def reset(self):
        """重置代理状态。"""
        self.conversation_history = []
        self.available_tools = []
        self.metrics = {
            'tokens_used': 0,
            'tools_loaded': 0,
            'api_calls': 0,
            'tools_called': []
        }


class PassiveToolAgent:
    """
    传统代理，预先注入所有工具（用于对比）。

    这种方法:
    1. 将所有工具模式注入初始提示词
    2. 巨大的上下文开销
    3. 将代理简化为被动工具选择器
    """

    def __init__(self, servers: Optional[List[ServerDefinition]] = None,
                 model: Optional[str] = None):
        # 获取统一 LLM 客户端
        if get_llm_client is not None:
            self.client = get_llm_client()
            self.model = self.client.model_name
        else:
            raise ImportError("无法导入 llm.client，请确保项目根目录的 .env 文件配置正确")

        # 覆盖模型（如果提供）
        if model:
            self.model = model

        # 预先加载所有工具
        self.servers = servers if servers is not None else create_tool_knowledge_base()
        self.all_tools = []
        for server in self.servers:
            self.all_tools.extend(server.tools)

        self.conversation_history = []
        self.metrics = {
            'tokens_used': 0,
            'tools_loaded': len(self.all_tools),
            'api_calls': 0,
            'tools_called': []
        }

    def execute_task(self, task: str) -> Dict[str, Any]:
        """使用所有预加载工具执行任务。"""
        self.conversation_history = []

        # 系统消息
        system_message = f"""你是一个可以访问多个域中 {len(self.all_tools)} 个工具的 AI 代理。

所有可用工具都已预加载。分析任务并使用适当的工具完成它。"""

        self.conversation_history.append({
            "role": "system",
            "content": system_message
        })

        self.conversation_history.append({
            "role": "user",
            "content": task
        })

        # 使用所有工具调用 LLM
        response = self._call_llm()
        self.metrics['api_calls'] += 1

        return {
            'response': response,
            'metrics': self.metrics,
            'tools_loaded': [t.name for t in self.all_tools],
            'conversation': self.conversation_history
        }

    def _call_llm(self) -> str:
        """使用所有注入的工具调用 LLM。"""
        kwargs = {
            "model": self.model,
            "messages": self.conversation_history,
            "temperature": config.AGENT_TEMPERATURE,
            "tools": [tool.to_schema() for tool in self.all_tools],
            "tool_choice": "auto"
        }

        response = self.client.chat.completions.create(**kwargs)

        # 跟踪 token 使用
        # response.usage 在 OpenAI SDK 中是 Optional: 属性始终存在
        # 但当提供者省略 token 计数时为 None
        if getattr(response, 'usage', None):
            self.metrics['tokens_used'] += response.usage.total_tokens

        message = response.choices[0].message

        # 处理工具调用（模拟）
        if message.tool_calls:
            return self._handle_tool_calls(message)

        return message.content or ""

    def _handle_tool_calls(self, message) -> str:
        """处理工具执行（模拟）。"""
        tool_results = []

        for tool_call in message.tool_calls:
            func_name = tool_call.function.name
            self.metrics['tools_called'].append(func_name)
            result = f"[模拟] 工具 '{func_name}' 成功执行"
            tool_results.append({
                "tool_call_id": tool_call.id,
                "output": result
            })

        # 添加到历史
        self.conversation_history.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
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
        })

        for result in tool_results:
            self.conversation_history.append({
                "role": "tool",
                "tool_call_id": result["tool_call_id"],
                "content": result["output"]
            })

        return self._call_llm()

    def reset(self):
        """重置代理状态。"""
        self.conversation_history = []
        self.metrics = {
            'tokens_used': 0,
            'tools_loaded': len(self.all_tools),
            'api_calls': 0,
            'tools_called': []
        }
