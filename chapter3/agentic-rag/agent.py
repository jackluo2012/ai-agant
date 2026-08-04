"""Agentic RAG 系统（ReAct 模式）"""

import sys
import os
import json
import logging
from typing import List, Dict, Any, Optional, Generator
from dataclasses import dataclass, field
from datetime import datetime

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from config import Config, AgentConfig
from tools import KnowledgeBaseTools, get_tool_definitions

# 导入统一 LLM 客户端
try:
    from llm.client import get_llm_client
except ImportError:
    get_llm_client = None
    logging.warning("无法导入 llm.client，请确保在项目根目录运行")


def _is_reasoning_model(model) -> bool:
    """判断是否为推理模型（如 Kimi K3、GPT-5 等）"""
    m = str(model or "").lower().replace("/", "-")
    return "kimi-k3" in m or "gpt-5" in m


def _reasoning_safe_temperature(model, requested=0.7):
    """推理模型只接受 temperature=1，其他模型使用请求的值"""
    return 1 if _is_reasoning_model(model) else requested


def _reasoning_safe_max_tokens(model, requested=2048, floor=4096):
    """推理模型需要更多 token，确保至少达到 floor 值"""
    if _is_reasoning_model(model):
        return max(requested, floor)
    return requested


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class Message:
    """对话消息"""
    role: str  # "user", "assistant", "tool"
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class AgenticRAG:
    """Agentic RAG 系统（ReAct 模式）"""

    # 默认 LLM 参数
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_MAX_TOKENS = 2048
    DEFAULT_STREAM = True

    def __init__(self, config: Optional[Config] = None):
        """初始化 Agent

        Args:
            config: 配置对象，如果为 None 则使用环境变量创建
        """
        self.config = config or Config.from_env()

        # 初始化 LLM 客户端
        self._init_llm_client()

        # 初始化知识库工具
        self.kb_tools = KnowledgeBaseTools(self.config.knowledge_base)

        # 对话历史
        self.conversation_history: List[Dict[str, Any]] = []

        # 工具定义
        self.tools = get_tool_definitions()

        logger.info(f"AgenticRAG 初始化完成，模型: {self.model}")

    def _init_llm_client(self):
        """初始化 LLM 客户端"""
        if get_llm_client is None:
            raise RuntimeError("LLM 客户端模块未加载，请确保在项目环境中运行")

        try:
            self.client = get_llm_client()
            self.model = self.client.model_name
            logger.info(f"使用模型: {self.model}")
        except Exception as e:
            logger.error(f"初始化 LLM 客户端失败: {e}")
            raise

    def _get_system_prompt(self) -> str:
        """生成系统提示词"""
        return """你是一个智能助手，可以访问知识库来回答问题。你的主要职责是基于知识库中的信息准确地回答用户的问题。

## 重要准则：

1. **仅使用知识库**：你必须只基于知识库中找到的信息来回答问题。如果信息不可用，请明确说明你无法根据现有知识回答。

2. **有效使用工具**：
   - 使用 `knowledge_base_search` 搜索相关信息
   - 使用 `get_document` 获取完整文档以获得更多上下文
   - 可能需要使用不同的查询进行多次搜索来完整回答问题

3. **必须引用**：在答案中始终包含引用。引用格式为 [文档: document_id] 或 [分块: chunk_id]。

4. **推理过程**：逐步思考：
   - 首先，理解需要什么信息
   - 搜索相关信息
   - 如需更多上下文，获取完整文档
   - 综合信息来回答问题
   - 包含适当的引用

5. **处理后续问题**：对于后续问题，考虑对话上下文，但始终从知识库验证信息。

6. **保持准确**：绝不编造信息。如果有内容不清楚或未找到，请明确说明。

记住：你的信誉取决于仅从知识库提供准确、有引用的信息。"""

    def _get_non_agentic_system_prompt(self) -> str:
        """非 Agentic 模式的系统提示词"""
        return """你是一个助手，基于知识库提供的上下文来回答问题。

重要规则：
1. 仅基于提供的上下文回答
2. 使用 [文档: document_id] 格式包含引用
3. 如果上下文不包含答案，请明确说明
4. 保持准确，不要编造信息"""

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行工具并返回结果

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        try:
            if tool_name == "knowledge_base_search":
                query = arguments.get("query", "")
                results = self.kb_tools.knowledge_base_search(query)

                # 详细模式下记录完整轨迹
                if self.config.agent.verbose:
                    logger.info("=" * 80)
                    logger.info(f"工具执行: {tool_name}")
                    logger.info("-" * 80)
                    logger.info(f"查询: {query}")
                    logger.info("-" * 80)

                if not results:
                    if self.config.agent.verbose:
                        logger.info("结果: 未找到相关文档")
                        logger.info("=" * 80)
                    return {"status": "no_results", "message": "未找到相关文档"}

                # 格式化结果 - 保留所有结果
                formatted_results = []
                for i, r in enumerate(results, 1):
                    formatted_results.append({
                        "doc_id": r["doc_id"],
                        "chunk_id": r["chunk_id"],
                        "text": r["text"],
                        "score": r["score"]
                    })

                    # 详细模式下记录每个结果
                    if self.config.agent.verbose:
                        logger.info(f"结果 {i}/{len(results)}:")
                        logger.info(f"  文档 ID: {r['doc_id']}")
                        logger.info(f"  分块 ID: {r['chunk_id']}")
                        logger.info(f"  得分: {r['score']:.4f}")
                        logger.info(f"  文本 (完整):\n{'-' * 40}")
                        logger.info(r['text'])
                        logger.info("-" * 40)

                if self.config.agent.verbose:
                    logger.info(f"共找到结果: {len(results)}")
                    logger.info("=" * 80)

                return {
                    "status": "success",
                    "results": formatted_results[:3],  # 限制为前 3 个用于 LLM 上下文
                    "total_found": len(results),
                    "all_results": formatted_results  # 保留所有用于日志
                }

            elif tool_name == "get_document":
                doc_id = arguments.get("doc_id", "")

                # 详细模式下记录完整轨迹
                if self.config.agent.verbose:
                    logger.info("=" * 80)
                    logger.info(f"工具执行: {tool_name}")
                    logger.info("-" * 80)
                    logger.info(f"文档 ID: {doc_id}")
                    logger.info("-" * 80)

                document = self.kb_tools.get_document(doc_id)

                if "error" in document:
                    if self.config.agent.verbose:
                        logger.info(f"错误: {document['error']}")
                        logger.info("=" * 80)
                    return {"status": "error", "message": document["error"]}

                # 记录完整文档内容
                if self.config.agent.verbose:
                    logger.info("已检索文档:")
                    logger.info(f"  文档 ID: {document.get('doc_id', doc_id)}")
                    if document.get('metadata'):
                        logger.info(f"  元数据: {json.dumps(document['metadata'], indent=2, ensure_ascii=False)}")
                    logger.info("  内容 (完整):\n" + "=" * 40)
                    logger.info(document.get('content', ''))
                    logger.info("=" * 80)

                return {
                    "status": "success",
                    "document": {
                        "doc_id": document.get("doc_id", doc_id),
                        "content": document.get("content", ""),
                        "metadata": document.get("metadata", {})
                    }
                }

            else:
                return {"status": "error", "message": f"未知工具: {tool_name}"}

        except Exception as e:
            logger.error(f"工具执行错误: {e}")
            return {"status": "error", "message": str(e)}

    def _build_messages(self, user_query: str) -> List[Dict[str, Any]]:
        """构建包含对话历史的消息列表

        Args:
            user_query: 用户查询

        Returns:
            消息列表
        """
        messages = [{"role": "system", "content": self._get_system_prompt()}]

        # 添加对话历史（限制数量）
        history_limit = self.config.agent.conversation_history_limit
        # limit<=0 → 无历史；list[-0:] 会包含所有轮次
        if history_limit > 0:
            if len(self.conversation_history) > history_limit:
                messages.extend(self.conversation_history[-history_limit:])
            else:
                messages.extend(self.conversation_history)

        # 添加当前用户查询
        messages.append({"role": "user", "content": user_query})

        return messages

    def query(self, user_query: str, stream: bool = None) -> Any:
        """使用 ReAct 模式处理用户查询

        Args:
            user_query: 用户的问题
            stream: 是否流式返回响应

        Returns:
            Agent 的响应（字符串或流式生成器）
        """
        if stream is None:
            stream = self.DEFAULT_STREAM

        # 构建消息
        messages = self._build_messages(user_query)

        # 跟踪迭代次数
        iterations = 0
        max_iterations = self.config.agent.max_iterations

        # ReAct 循环处理
        while iterations < max_iterations:
            iterations += 1

            if self.config.agent.verbose:
                logger.info("\n" + "=" * 100)
                logger.info(f"迭代 {iterations}/{max_iterations}")
                logger.info("=" * 100)

            try:
                # 调用 LLM（带工具）
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                    temperature=_reasoning_safe_temperature(self.model, self.DEFAULT_TEMPERATURE),
                    max_tokens=_reasoning_safe_max_tokens(self.model, self.DEFAULT_MAX_TOKENS),
                    stream=False  # 单独处理流式输出
                )

                message = response.choices[0].message

                # 添加助手消息到历史
                assistant_msg = {"role": "assistant", "content": message.content or ""}
                if message.tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in message.tool_calls
                    ]
                messages.append(assistant_msg)

                # 处理工具调用
                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        try:
                            arguments = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            arguments = {}

                        if self.config.agent.verbose:
                            logger.info("\n" + "#" * 80)
                            logger.info(f"工具调用: {tool_name}")
                            logger.info(f"参数: {json.dumps(arguments, indent=2, ensure_ascii=False)}")
                            logger.info("#" * 80)

                        # 执行工具
                        result = self._execute_tool(tool_name, arguments)

                        # 详细模式下记录完整工具结果
                        if self.config.agent.verbose:
                            logger.info("\n" + "*" * 80)
                            logger.info("工具结果:")
                            logger.info("*" * 80)
                            if 'all_results' in result:
                                logger.info("所有搜索结果（完整）:")
                                for idx, res in enumerate(result['all_results'], 1):
                                    logger.info(f"\n结果 {idx}:")
                                    logger.info(json.dumps(res, indent=2, ensure_ascii=False))
                            else:
                                logger.info(json.dumps(result, indent=2, ensure_ascii=False))
                            logger.info("*" * 80 + "\n")

                        # 消息中不包含 all_results 以避免过载 LLM
                        result_for_llm = {k: v for k, v in result.items() if k != 'all_results'}

                        # 添加工具结果到消息
                        tool_message = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result_for_llm, ensure_ascii=False)
                        }
                        messages.append(tool_message)

                    # 继续下一轮迭代
                    continue
                else:
                    # 无工具调用，获得最终答案
                    # 更新对话历史
                    self.conversation_history.append({"role": "user", "content": user_query})
                    self.conversation_history.append(assistant_msg)

                    # 返回响应
                    if stream:
                        return self._stream_response(message.content or "")
                    else:
                        return message.content or ""

            except Exception as e:
                logger.error(f"查询处理错误: {e}")
                error_msg = f"处理查询时出错: {str(e)}"
                if stream:
                    return self._stream_response(error_msg)
                else:
                    return error_msg

        # 达到最大迭代次数
        logger.warning(f"达到最大迭代次数 ({max_iterations})")
        final_msg = "需要更多迭代来完整回答你的问题。请尝试重新表述或将问题拆分。"

        if stream:
            return self._stream_response(final_msg)
        else:
            return final_msg

    def _stream_response(self, content: str) -> Generator[str, None, None]:
        """流式返回响应内容"""
        for char in content:
            yield char

    def query_non_agentic(self, user_query: str, stream: bool = None) -> Any:
        """非 Agentic RAG 模式：简单检索 + LLM 响应

        Args:
            user_query: 用户的问题
            stream: 是否流式返回响应

        Returns:
            响应（字符串或流式生成器）
        """
        if stream is None:
            stream = self.DEFAULT_STREAM

        try:
            # 简单检索
            search_results = self.kb_tools.knowledge_base_search(user_query)

            # 从搜索结果构建上下文
            context_parts = []
            for i, result in enumerate(search_results[:3], 1):  # 前 3 个结果
                context_parts.append(
                    f"[文档 {i}] (ID: {result['doc_id']}, 分块: {result['chunk_id']})\n{result['text']}\n"
                )

            if not context_parts:
                context = "知识库中未找到相关信息。"
            else:
                context = "\n".join(context_parts)

            # 构建提示词
            user_prompt = f"""知识库上下文：
{context}

用户问题: {user_query}

请仅基于提供的上下文回答问题。包含引用。"""

            # 调用 LLM
            messages = [
                {"role": "system", "content": self._get_non_agentic_system_prompt()},
                {"role": "user", "content": user_prompt}
            ]

            if stream:
                response_stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=_reasoning_safe_temperature(self.model, self.DEFAULT_TEMPERATURE),
                    max_tokens=_reasoning_safe_max_tokens(self.model, self.DEFAULT_MAX_TOKENS),
                    stream=True
                )

                def response_generator():
                    for chunk in response_stream:
                        if chunk.choices[0].delta.content:
                            yield chunk.choices[0].delta.content

                return response_generator()
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=_reasoning_safe_temperature(self.model, self.DEFAULT_TEMPERATURE),
                    max_tokens=_reasoning_safe_max_tokens(self.model, self.DEFAULT_MAX_TOKENS),
                    stream=False
                )
                return response.choices[0].message.content

        except Exception as e:
            logger.error(f"非 Agentic 查询错误: {e}")
            error_msg = f"处理查询时出错: {str(e)}"
            if stream:
                return self._stream_response(error_msg)
            else:
                return error_msg

    def clear_history(self):
        """清除对话历史"""
        self.conversation_history = []
        logger.info("对话历史已清除")
