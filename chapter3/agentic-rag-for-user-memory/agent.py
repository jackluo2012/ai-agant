"""面向用户记忆评估的 Agentic RAG 智能体

该智能体使用 RAG 索引的对话记忆来回答关于用户交互的问题，
遵循 ReAct 模式。
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

import json
import logging
from typing import List, Dict, Any, Optional, Generator
from dataclasses import dataclass, field
from datetime import datetime

from config import Config
from tools import MemoryTools, get_tool_definitions
from indexer import MemoryIndexer

try:
    from llm.client import get_llm_client
except ImportError:
    get_llm_client = None
    logging.warning("无法导入 llm.client，将使用备用配置")


def _reasoning_safe_temperature(model, requested=1.0):
    """推理模型（如 Kimi K3、GPT-5 等）只接受 temperature=1。
    对于这些模型返回 1，其他模型保持请求的值，以便非推理
    提供商（豆包、DeepSeek、旧版 Moonshot）保持不变。"""
    m = str(model or "").lower().replace("/", "-")
    return 1 if ("kimi-k3" in m or "gpt-5" in m) else requested


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class Message:
    """表示对话中的一条消息"""
    role: str  # "user", "assistant", "tool"
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AgentTrajectory:
    """跟踪智能体的推理和工具使用"""
    test_id: str
    question: str
    iterations: List[Dict[str, Any]] = field(default_factory=list)
    final_answer: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    total_time: Optional[float] = None
    success: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "question": self.question,
            "iterations": self.iterations,
            "final_answer": self.final_answer,
            "tool_calls": self.tool_calls,
            "total_time": self.total_time,
            "success": self.success,
            "total_iterations": len(self.iterations),
            "total_tool_calls": len(self.tool_calls)
        }


class UserMemoryRAGAgent:
    """使用 RAG 回答用户对话历史问题的智能体"""

    def __init__(self,
                 indexer: MemoryIndexer,
                 config: Optional[Config] = None):
        """
        初始化智能体

        Args:
            indexer: 已加载对话的记忆索引器
            config: 配置对象
        """
        self.config = config or Config.from_env()
        self.indexer = indexer
        self.memory_tools = MemoryTools(indexer)

        # 初始化 LLM 客户端
        self._init_llm_client()

        # 工具定义
        self.tools = get_tool_definitions()

        # 对话历史
        self.conversation_history: List[Dict[str, Any]] = []

        logger.info(f"已初始化 UserMemoryRAGAgent，使用模型: {self.model}")

    def _init_llm_client(self):
        """初始化 LLM 客户端"""
        if get_llm_client is not None:
            # 使用统一的 LLM 客户端
            self.client = get_llm_client()
            self.model = self.client.model_name
            logger.info(f"使用统一 LLM 客户端，模型: {self.model}")
        else:
            # 备用方案：使用 config 中的配置
            from openai import OpenAI
            client_config, model = self.config.llm.get_client_config()
            base_url = client_config.pop("base_url", None)
            if base_url:
                self.client = OpenAI(base_url=base_url, **client_config)
            else:
                self.client = OpenAI(**client_config)
            self.model = model
            logger.info(f"使用备用 LLM 客户端，模型: {self.model}")

    def _get_system_prompt(self, test_id: str) -> str:
        """生成系统提示词"""
        return f"""你是一个 AI 助手，可以访问来自用户交互的索引对话记忆。
你的任务是仅根据你在索引记忆中找到的信息，准确回答这些对话的相关问题。

当前测试用例：{test_id}

## 重要指南：

1. **仅记忆搜索**：你必须只根据通过记忆搜索工具找到的信息来回答。如果索引对话中没有该信息，请明确说明你找不到它。

2. **有效使用工具**：
   - 使用 `search_memory` 在所有对话中查找相关信息
   - 当需要更多搜索结果上下文时，使用 `get_conversation_context`
   - 需要查看完整对话历史时使用 `get_full_conversation`

3. **多次搜索**：不要犹豫，使用不同的查询执行多次搜索以找到所有相关信息。不同的表述可能会产生不同的结果。

4. **引用要求**：提供答案时，始终说明你是在哪个对话或块中找到的信息。

5. **全面考虑**：对于复杂问题，在制定答案之前，从多个块和对话中收集信息。

6. **处理歧义**：如果发现冲突信息或多个可能的答案，请报告所有答案及其来源。

记住：你的可信度取决于仅从对话记忆中提供准确、有来源的信息。"""

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行工具并返回结果"""
        try:
            # 记录工具调用参数到控制台
            logger.info("="*80)
            logger.info(f"工具调用: {tool_name}")
            logger.info(f"参数: {json.dumps(arguments, indent=2, ensure_ascii=False)}")
            logger.info("-"*80)

            if tool_name == "search_memory":
                query = arguments.get("query", "")
                filter_test_id = arguments.get("filter_test_id")

                result = self.memory_tools.search_memory(
                    query,
                    top_k=self.config.agent.max_search_results,
                    filter_test_id=filter_test_id,
                )

                # 记录结果到控制台
                result_dict = result.to_dict()
                logger.info("工具结果:")
                logger.info(json.dumps(result_dict, indent=2, ensure_ascii=False))
                logger.info("="*80)

                return result_dict

            elif tool_name == "get_conversation_context":
                chunk_id = arguments.get("chunk_id", "")
                context_size = arguments.get("context_size", 2)

                result = self.memory_tools.get_conversation_context(chunk_id, context_size)

                # 记录结果到控制台
                result_dict = result.to_dict()
                logger.info("工具结果:")
                logger.info(json.dumps(result_dict, indent=2, ensure_ascii=False))
                logger.info("="*80)

                return result_dict

            elif tool_name == "get_full_conversation":
                conversation_id = arguments.get("conversation_id", "")
                test_id = arguments.get("test_id", "")

                result = self.memory_tools.get_full_conversation(conversation_id, test_id)

                # 记录结果到控制台
                result_dict = result.to_dict()
                logger.info("工具结果:")
                logger.info(json.dumps(result_dict, indent=2, ensure_ascii=False))
                logger.info("="*80)

                return result_dict

            else:
                return {"status": "error", "error": f"未知工具: {tool_name}"}

        except Exception as e:
            logger.error(f"工具执行错误: {e}")
            return {"status": "error", "error": str(e)}

    def answer_question(self,
                       question: str,
                       test_id: str,
                       stream: bool = False) -> Dict[str, Any]:
        """
        使用 RAG 回答关于用户对话历史的问题

        Args:
            question: 要回答的问题
            test_id: 用于上下文的测试用例 ID
            stream: 是否流式返回响应

        Returns:
            包含答案和轨迹的字典
        """
        start_time = datetime.now()
        trajectory = AgentTrajectory(test_id=test_id, question=question)

        # 构建初始消息
        messages = [
            {"role": "system", "content": self._get_system_prompt(test_id)},
            {"role": "user", "content": question}
        ]

        # 跟踪迭代
        iterations = 0
        max_iterations = self.config.evaluation.max_iterations

        # 使用 ReAct 循环处理
        while iterations < max_iterations:
            iterations += 1
            iteration_data = {"iteration": iterations, "timestamp": datetime.now().isoformat()}

            if self.config.agent.enable_reasoning:
                logger.info(f"\n{'='*60}")
                logger.info(f"迭代 {iterations}/{max_iterations}")
                logger.info(f"{'='*60}")

            try:
                # 调用 LLM 并传递工具
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                    temperature=_reasoning_safe_temperature(self.model, self.config.llm.temperature),
                    max_tokens=self.config.llm.max_tokens,
                    stream=False
                )

                message = response.choices[0].message
                iteration_data["assistant_message"] = message.content or ""

                # 记录 LLM 响应内容
                if message.content:
                    logger.info("-"*60)
                    logger.info(f"LLM 响应: {message.content}")
                    logger.info("-"*60)

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
                    iteration_data["tool_calls"] = []

                messages.append(assistant_msg)

                # 处理工具调用
                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        try:
                            arguments = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            arguments = {}

                        # 执行工具
                        result = self._execute_tool(tool_name, arguments)

                        # 跟踪工具调用
                        tool_call_data = {
                            "tool": tool_name,
                            "arguments": arguments,
                            "result": result,
                            "timestamp": datetime.now().isoformat()
                        }
                        iteration_data["tool_calls"].append(tool_call_data)
                        trajectory.tool_calls.append(tool_call_data)

                        # 添加工具结果到消息
                        tool_message = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result, ensure_ascii=False)
                        }
                        messages.append(tool_message)

                    # 继续下一次迭代
                    trajectory.iterations.append(iteration_data)
                    continue
                else:
                    # 没有工具调用，得到最终答案
                    trajectory.iterations.append(iteration_data)
                    trajectory.final_answer = message.content or ""
                    trajectory.success = True

                    # 计算总时间
                    end_time = datetime.now()
                    trajectory.total_time = (end_time - start_time).total_seconds()

                    # 返回结果
                    result = {
                        "answer": trajectory.final_answer,
                        "success": True,
                        "iterations": iterations,
                        "tool_calls": len(trajectory.tool_calls),
                        "trajectory": trajectory.to_dict() if self.config.evaluation.save_trajectories else None
                    }

                    if stream:
                        return self._stream_response(result)
                    else:
                        return result

            except Exception as e:
                logger.error(f"迭代 {iterations} 中出错: {e}")
                trajectory.iterations.append({
                    "iteration": iterations,
                    "error": str(e)
                })

                # 继续下一次迭代
                continue

        # 达到最大迭代次数
        logger.warning(f"已达到最大迭代次数 ({max_iterations})")

        # 计算总时间
        end_time = datetime.now()
        trajectory.total_time = (end_time - start_time).total_seconds()
        trajectory.success = False

        final_msg = "我无法在迭代限制内找到足够的信息来回答你的问题。请尝试重新表述或分解你的查询。"

        return {
            "answer": final_msg,
            "success": False,
            "iterations": iterations,
            "tool_calls": len(trajectory.tool_calls),
            "trajectory": trajectory.to_dict() if self.config.evaluation.save_trajectories else None
        }

    def _stream_response(self, result: Dict[str, Any]) -> Generator[str, None, None]:
        """流式返回响应内容"""
        answer = result.get("answer", "")
        for char in answer:
            yield char

    def clear_history(self):
        """清除对话历史"""
        self.conversation_history = []
        logger.info("对话历史已清除")

    def save_trajectory(self, trajectory: AgentTrajectory, filepath: str):
        """
        保存智能体轨迹到文件

        Args:
            trajectory: 要保存的轨迹
            filepath: 保存轨迹的文件路径
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(trajectory.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"轨迹已保存到 {filepath}")
