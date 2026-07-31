"""
上下文压缩策略模块
==================

本模块实现了多种上下文压缩策略，用于对比不同方法的效果。

支持的压缩策略:
    - NO_COMPRESSION: 无压缩（基线）
    - NON_CONTEXT_AWARE_INDIVIDUAL: 非上下文感知 - 逐页摘要
    - NON_CONTEXT_AWARE_COMBINED: 非上下文感知 - 合并摘要
    - CONTEXT_AWARE: 上下文感知摘要
    - CONTEXT_AWARE_CITATIONS: 带引用的上下文感知摘要
    - WINDOWED_CONTEXT: 窗口化上下文
"""

import json
import logging
from typing import List, Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from openai import OpenAI
import tiktoken

# 导入项目通用 LLM 客户端
import sys
import os

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

try:
    from chapter2.context_compression.config import Config
except ImportError:
    from config import Config

# 配置日志
logger = logging.getLogger(__name__)


def _is_reasoning_model(model: str) -> bool:
    """
    判断是否为推理模型

    Args:
        model: 模型名称

    Returns:
        如果是推理模型返回 True
    """
    m = str(model or "").lower()
    return "kimi-k3" in m or "gpt-5" in m or "claude" in m


def _get_safe_temperature(model: str, requested: float = 0.3) -> float:
    """
    获取安全的温度参数

    推理模型（Kimi K3、GPT-5）只接受 temperature=1

    Args:
        model: 模型名称
        requested: 请求的温度值

    Returns:
        安全的温度参数值
    """
    return 1.0 if _is_reasoning_model(model) else requested


def _get_safe_max_tokens(model: str, requested: int, reasoning_budget: int = 2048) -> int:
    """
    获取安全的最大 token 数

    推理模型需要额外的推理预算，因为部分 token 会用于推理过程

    Args:
        model: 模型名称
        requested: 请求的 token 数
        reasoning_budget: 推理预算

    Returns:
        调整后的 token 数
    """
    if _is_reasoning_model(model):
        return requested + reasoning_budget
    return requested


class CompressionStrategy(Enum):
    """上下文压缩策略枚举"""

    NO_COMPRESSION = "no_compression"
    """无压缩 - 返回原始内容"""

    NON_CONTEXT_AWARE_INDIVIDUAL = "non_context_aware_individual_summary"
    """非上下文感知 - 逐页摘要后拼接"""

    NON_CONTEXT_AWARE_COMBINED = "non_context_aware_combined_summary"
    """非上下文感知 - 合并全部内容后摘要"""

    CONTEXT_AWARE = "context_aware_summary"
    """上下文感知 - 基于查询的聚焦摘要"""

    CONTEXT_AWARE_CITATIONS = "context_aware_with_citations"
    """上下文感知带引用 - 包含来源链接"""

    WINDOWED_CONTEXT = "windowed_context"
    """窗口化上下文 - 保留最新完整内容，压缩历史"""


@dataclass
class CompressedContent:
    """
    压缩内容数据类

    Attributes:
        original_length: 原始内容长度
        compressed_length: 压缩后内容长度
        content: 压缩后的内容
        citations: 引用列表
        strategy: 使用的压缩策略
        timestamp: 压缩时间戳
    """
    original_length: int
    compressed_length: int
    content: str
    citations: List[Dict[str, str]] = field(default_factory=list)
    strategy: CompressionStrategy = CompressionStrategy.NO_COMPRESSION
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def compression_ratio(self) -> float:
        """压缩比（压缩后/原始）"""
        if self.original_length == 0:
            return 0.0
        return (self.compressed_length / self.original_length) * 100


class ContextCompressor:
    """
    上下文压缩器

    处理不同策略的上下文压缩

    Attributes:
        strategy: 压缩策略
        enable_streaming: 是否启用流式输出
        client: LLM 客户端
        model: 模型名称
        encoding: token 编码器
    """

    def __init__(
        self,
        strategy: CompressionStrategy,
        enable_streaming: bool = True
    ):
        """
        初始化上下文压缩器

        Args:
            strategy: 压缩策略
            enable_streaming: 是否启用流式输出
        """
        self.strategy = strategy
        self.enable_streaming = enable_streaming

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

        # 初始化 token 计数器
        try:
            self.encoding = tiktoken.encoding_for_model("gpt-4")
        except:
            self.encoding = tiktoken.get_encoding("cl100k_base")

        logger.info(f"上下文压缩器初始化完成 - 策略: {strategy.value}, 流式: {enable_streaming}")

    def count_tokens(self, text: str) -> int:
        """
        计算 token 数量

        Args:
            text: 待计算文本

        Returns:
            token 数量
        """
        try:
            return len(self.encoding.encode(text))
        except:
            # 回退到字符估算（1 token ≈ 4 字符）
            return len(text) // 4

    def compress_search_results(
        self,
        search_results: Dict[str, Any],
        query: str,
        current_context: Optional[str] = None
    ) -> CompressedContent:
        """
        根据选定策略压缩搜索结果

        Args:
            search_results: 原始搜索结果
            query: 原始搜索查询
            current_context: 当前对话上下文（用于上下文感知策略）

        Returns:
            压缩后的内容
        """
        logger.debug(f"压缩策略: {self.strategy}, 类型: {type(self.strategy)}, 值: {self.strategy.value if hasattr(self.strategy, 'value') else 'N/A'}")
        logger.debug(f"CompressionStrategy 枚举 id: {id(CompressionStrategy)}")
        logger.debug(f"CompressionStrategy.CONTEXT_AWARE id: {id(CompressionStrategy.CONTEXT_AWARE)}")

        # 使用值比较而不是枚举比较
        strategy_value = self.strategy.value if hasattr(self.strategy, 'value') else str(self.strategy)

        if strategy_value == CompressionStrategy.NO_COMPRESSION.value:
            return self._no_compression(search_results)
        elif strategy_value == CompressionStrategy.NON_CONTEXT_AWARE_INDIVIDUAL.value:
            return self._non_context_aware_individual_summary(search_results)
        elif strategy_value == CompressionStrategy.NON_CONTEXT_AWARE_COMBINED.value:
            return self._non_context_aware_combined_summary(search_results)
        elif strategy_value == CompressionStrategy.CONTEXT_AWARE.value:
            return self._context_aware_summary(search_results, query, current_context)
        elif strategy_value == CompressionStrategy.CONTEXT_AWARE_CITATIONS.value:
            return self._context_aware_with_citations(search_results, query, current_context)
        elif strategy_value == CompressionStrategy.WINDOWED_CONTEXT.value:
            # 窗口化策略返回完整内容（压缩稍后进行）
            return self._no_compression(search_results)
        else:
            logger.error(f"未知的压缩策略: {self.strategy}")
            logger.error(f"策略类型: {type(self.strategy)}")
            logger.error(f"策略值: {strategy_value}")
            raise ValueError(f"未知的压缩策略: {self.strategy}")

    def compress_for_history(
        self,
        content: str,
        tool_name: str,
        query: str,
        preserve_citations: bool = True
    ) -> CompressedContent:
        """
        压缩消息历史内容（用于窗口化策略）

        Args:
            content: 待压缩内容
            tool_name: 生成该内容的工具名称
            query: 触发工具调用的查询
            preserve_citations: 是否保留引用

        Returns:
            压缩后的内容
        """
        original_length = len(content)

        try:
            prompt = f"""请将以下 {tool_name} 的结果压缩为简洁的摘要，保留关键信息。

重点关注与以下查询相关的信息：{query}

原始内容：
{content[:10000]}

要求：
1. 保留所有重要事实、姓名、日期和关联信息
2. 删除冗余信息
3. 保持清晰连贯
{"4. 为重要事实包含 [来源: URL] 引用" if preserve_citations else ""}
5. 最大长度：{Config.SUMMARY_MAX_TOKENS} tokens

请提供聚焦的摘要："""

            # 记录提示词长度
            prompt_tokens = self.count_tokens(prompt)
            logger.info(f"简单摘要请求 - 提示词 tokens: {prompt_tokens}, 提示词长度: {len(prompt)} 字符")

            if self.enable_streaming:
                # 流式输出摘要
                print(f"\n📝 正在创建简单摘要...\n", flush=True)
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个擅长创建简洁摘要的助手。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_get_safe_temperature(self.model, 0.3),
                    max_tokens=_get_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS),
                    stream=True
                )

                summary_parts = []
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        delta_text = chunk.choices[0].delta.content
                        print(delta_text, end="", flush=True)
                        summary_parts.append(delta_text)
                print("\n")  # 流式输出后换行
                compressed = "".join(summary_parts)
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个擅长创建简洁摘要的助手。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_get_safe_temperature(self.model, 0.3),
                    max_tokens=_get_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS)
                )
                compressed = response.choices[0].message.content

            return CompressedContent(
                original_length=original_length,
                compressed_length=len(compressed),
                content=compressed,
                strategy=CompressionStrategy.WINDOWED_CONTEXT
            )

        except Exception as e:
            logger.error(f"历史内容压缩错误: {str(e)}")
            # 回退到截断
            truncated = content[:2000] + "\n\n[内容因历史记录已截断...]"
            return CompressedContent(
                original_length=original_length,
                compressed_length=len(truncated),
                content=truncated,
                strategy=CompressionStrategy.WINDOWED_CONTEXT
            )

    # ==================== 策略实现 ====================

    def _no_compression(self, search_results: Dict[str, Any]) -> CompressedContent:
        """
        策略 1：无压缩 - 返回所有原始内容
        """
        all_content = []
        total_length = 0

        for result in search_results.get('results', []):
            content = f"""
===== 搜索结果 =====
标题: {result.get('title', 'N/A')}
链接: {result.get('url', 'N/A')}
摘要: {result.get('snippet', 'N/A')}

完整内容:
{result.get('content', '无内容')}
========================
"""
            all_content.append(content)
            total_length += len(result.get('content', ''))

        full_content = "\n\n".join(all_content)

        return CompressedContent(
            original_length=total_length,
            compressed_length=len(full_content),
            content=full_content,
            strategy=CompressionStrategy.NO_COMPRESSION
        )

    def _non_context_aware_individual_summary(self, search_results: Dict[str, Any]) -> CompressedContent:
        """
        策略 2A：非上下文感知 - 逐页摘要后拼接
        """
        summaries = []
        total_original = 0

        for result in search_results.get('results', []):
            if not result.get('content'):
                continue

            original_content = result.get('content', '')
            total_original += len(original_content)

            try:
                # 对每页独立摘要
                prompt = f"""请用 2-3 段话总结以下网页内容：

标题: {result.get('title', 'N/A')}
链接: {result.get('url', 'N/A')}

内容:
{original_content[:5000]}

请提供简洁的摘要："""

                prompt_tokens = self.count_tokens(prompt)
                logger.info(f"非上下文感知摘要 - 提示词 tokens: {prompt_tokens}, 提示词长度: {len(prompt)} 字符")

                if self.enable_streaming:
                    print(f"\n📝 正在摘要: {result.get('title', 'N/A')[:50]}...", end=" ", flush=True)
                    stream = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "你是一个擅长创建简洁摘要的助手。"},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=_get_safe_temperature(self.model, 0.3),
                        max_tokens=_get_safe_max_tokens(self.model, 300),
                        stream=True
                    )

                    summary_parts = []
                    for chunk in stream:
                        if chunk.choices and chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            print(content, end="", flush=True)
                            summary_parts.append(content)
                    print()  # 流式输出后换行
                    summary = "".join(summary_parts)
                else:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "你是一个擅长创建简洁摘要的助手。"},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=_get_safe_temperature(self.model, 0.3),
                        max_tokens=_get_safe_max_tokens(self.model, 300)
                    )
                    summary = response.choices[0].message.content

                summaries.append(f"""
来源: {result.get('title', 'N/A')}
链接: {result.get('url', 'N/A')}
摘要: {summary}
""")

            except Exception as e:
                logger.error(f"页面摘要错误: {str(e)}")
                # 回退到使用摘要片段
                summaries.append(f"""
来源: {result.get('title', 'N/A')}
链接: {result.get('url', 'N/A')}
摘要: {result.get('snippet', '无摘要可用')}
""")

        compressed_content = "\n".join(summaries)

        return CompressedContent(
            original_length=total_original,
            compressed_length=len(compressed_content),
            content=compressed_content,
            strategy=CompressionStrategy.NON_CONTEXT_AWARE_INDIVIDUAL
        )

    def _non_context_aware_combined_summary(self, search_results: Dict[str, Any]) -> CompressedContent:
        """
        策略 2B：非上下文感知 - 合并全部内容后摘要
        """
        # 先合并所有内容
        all_content = []
        total_original = 0
        max_chars_per_page = 5000  # 限制每页长度防止 token 溢出

        for result in search_results.get('results', []):
            if result.get('content'):
                original_content = result.get('content', '')
                total_original += len(original_content)

                # 限制每页内容
                limited_content = original_content[:max_chars_per_page]

                all_content.append(f"""
===== 页面: {result.get('title', 'N/A')} =====
链接: {result.get('url', 'N/A')}
内容: {limited_content}
""")

        if not all_content:
            return CompressedContent(
                original_length=0,
                compressed_length=0,
                content="无可用内容",
                strategy=CompressionStrategy.NON_CONTEXT_AWARE_COMBINED
            )

        combined_content = "\n\n".join(all_content)

        try:
            # 创建合并内容的摘要
            prompt = f"""请全面总结以下合并的网页内容：

{combined_content}

要求：
1. 创建涵盖所有页面的全面摘要
2. 包含每个来源的关键信息
3. 保持事实准确性
4. 最大长度：{Config.SUMMARY_MAX_TOKENS} tokens

请提供全面的摘要："""

            prompt_tokens = self.count_tokens(prompt)
            logger.info(f"非上下文感知合并摘要 - 提示词 tokens: {prompt_tokens}, 提示词长度: {len(prompt)} 字符")

            if self.enable_streaming:
                print(f"\n📄 正在创建全部 {len(search_results.get('results', []))} 个页面的合并摘要...\n", flush=True)
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个擅长创建全面摘要的助手。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_get_safe_temperature(self.model, 0.3),
                    max_tokens=_get_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS),
                    stream=True
                )

                summary_parts = []
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        print(content, end="", flush=True)
                        summary_parts.append(content)
                print("\n")  # 流式输出后换行
                summary = "".join(summary_parts)
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个擅长创建全面摘要的助手。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_get_safe_temperature(self.model, 0.3),
                    max_tokens=_get_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS)
                )
                summary = response.choices[0].message.content

            return CompressedContent(
                original_length=total_original,
                compressed_length=len(summary),
                content=summary,
                strategy=CompressionStrategy.NON_CONTEXT_AWARE_COMBINED
            )

        except Exception as e:
            logger.error(f"合并摘要创建错误: {str(e)}")
            # 回退到拼接摘要片段
            fallback = "\n\n".join([
                f"{r.get('title', 'N/A')}: {r.get('snippet', '无摘要可用')}"
                for r in search_results.get('results', [])
            ])
            return CompressedContent(
                original_length=total_original,
                compressed_length=len(fallback),
                content=fallback,
                strategy=CompressionStrategy.NON_CONTEXT_AWARE_COMBINED
            )

    def _context_aware_summary(
        self,
        search_results: Dict[str, Any],
        query: str,
        current_context: Optional[str] = None
    ) -> CompressedContent:
        """
        策略 3：上下文感知 - 基于查询的聚焦摘要
        """
        # 合并所有内容，每页限制长度
        all_content = []
        total_original = 0
        max_chars_per_page = 5000

        for result in search_results.get('results', []):
            if result.get('content'):
                original_content = result.get('content', '')
                total_original += len(original_content)

                limited_content = original_content[:max_chars_per_page]

                all_content.append(f"""
标题: {result.get('title', 'N/A')}
链接: {result.get('url', 'N/A')}
内容: {limited_content}
""")

        combined_content = "\n\n".join(all_content)

        try:
            # 创建上下文感知摘要
            prompt = f"""基于搜索查询："{query}"
{f"当前上下文：{current_context[:1000]}" if current_context else ""}

请分析以下搜索结果，并提供直接回答查询的聚焦摘要。
重点提取与回答以下问题最相关的信息：{query}

搜索结果：
{combined_content}

要求：
1. 只关注与查询相关的信息
2. 优先考虑当前/近期信息
3. 包含具体姓名、日期和关联信息
4. 最大长度：{Config.SUMMARY_MAX_TOKENS} tokens

请提供查询聚焦的摘要："""

            prompt_tokens = self.count_tokens(prompt)
            logger.info(f"上下文感知摘要 - 提示词 tokens: {prompt_tokens}, 提示词长度: {len(prompt)} 字符")

            if self.enable_streaming:
                print(f"\n🎯 正在为查询创建上下文感知摘要: '{query[:50]}...'\n", flush=True)
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个擅长创建聚焦、上下文感知摘要的助手。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_get_safe_temperature(self.model, 0.3),
                    max_tokens=_get_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS),
                    stream=True
                )

                summary_parts = []
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        print(content, end="", flush=True)
                        summary_parts.append(content)
                print("\n")  # 流式输出后换行
                summary = "".join(summary_parts)
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个擅长创建聚焦、上下文感知摘要的助手。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_get_safe_temperature(self.model, 0.3),
                    max_tokens=_get_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS)
                )
                summary = response.choices[0].message.content

            return CompressedContent(
                original_length=total_original,
                compressed_length=len(summary),
                content=summary,
                strategy=CompressionStrategy.CONTEXT_AWARE
            )

        except Exception as e:
            logger.error(f"上下文感知摘要创建错误: {str(e)}")
            # 回退到简单拼接
            fallback = "\n\n".join([r.get('snippet', '') for r in search_results.get('results', [])])
            return CompressedContent(
                original_length=total_original,
                compressed_length=len(fallback),
                content=fallback,
                strategy=CompressionStrategy.CONTEXT_AWARE
            )

    def _context_aware_with_citations(
        self,
        search_results: Dict[str, Any],
        query: str,
        current_context: Optional[str] = None
    ) -> CompressedContent:
        """
        策略 4：上下文感知带引用 - 包含来源链接的摘要
        """
        # 跟踪来源，每页限制长度
        sources = []
        all_content = []
        total_original = 0
        max_chars_per_page = 5000

        for i, result in enumerate(search_results.get('results', [])):
            if result.get('content'):
                source_id = f"[{i+1}]"
                original_content = result.get('content', '')
                total_original += len(original_content)

                limited_content = original_content[:max_chars_per_page]

                sources.append({
                    'id': source_id,
                    'title': result.get('title', 'N/A'),
                    'url': result.get('url', 'N/A')
                })

                all_content.append(f"""
{source_id} 标题: {result.get('title', 'N/A')}
内容: {limited_content}
""")

        combined_content = "\n\n".join(all_content)

        try:
            # 创建带引用的上下文感知摘要
            prompt = f"""基于搜索查询："{query}"
{f"当前上下文：{current_context[:1000]}" if current_context else ""}

请分析以下搜索结果，并提供带引用的聚焦摘要。

搜索结果（带来源 ID）：
{combined_content}

要求：
1. 关注与以下查询相关的信息：{query}
2. 对每个事实使用内联引用 [1]、[2] 等
3. 优先考虑当前/近期信息
4. 包含具体姓名、日期和关联信息及其引用
5. 最大长度：{Config.SUMMARY_MAX_TOKENS} tokens

请提供带引用的查询聚焦摘要："""

            prompt_tokens = self.count_tokens(prompt)
            logger.info(f"基于引用的摘要 - 提示词 tokens: {prompt_tokens}, 提示词长度: {len(prompt)} 字符")

            if self.enable_streaming:
                print(f"\n📚 正在为以下查询创建带引用的摘要: '{query[:50]}...'\n", flush=True)
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个擅长创建带适当引用的聚焦摘要的助手。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_get_safe_temperature(self.model, 0.3),
                    max_tokens=_get_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS),
                    stream=True
                )

                summary_parts = []
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        print(content, end="", flush=True)
                        summary_parts.append(content)
                print("\n")  # 流式输出后换行
                summary = "".join(summary_parts)
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个擅长创建带适当引用的聚焦摘要的助手。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_get_safe_temperature(self.model, 0.3),
                    max_tokens=_get_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS)
                )
                summary = response.choices[0].message.content

            # 附加来源列表
            source_list = "\n\n来源：\n"
            for source in sources:
                source_list += f"{source['id']} {source['title']} - {source['url']}\n"

            final_content = summary + source_list

            return CompressedContent(
                original_length=total_original,
                compressed_length=len(final_content),
                content=final_content,
                citations=sources,
                strategy=CompressionStrategy.CONTEXT_AWARE_CITATIONS
            )

        except Exception as e:
            logger.error(f"带引用摘要创建错误: {str(e)}")
            # 回退
            fallback = "\n\n".join([
                f"[{i+1}] {r.get('title', '')}: {r.get('snippet', '')}"
                for i, r in enumerate(search_results.get('results', []))
            ])
            return CompressedContent(
                original_length=total_original,
                compressed_length=len(fallback),
                content=fallback,
                citations=sources,
                strategy=CompressionStrategy.CONTEXT_AWARE_CITATIONS
            )
