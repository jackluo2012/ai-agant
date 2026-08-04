"""面向用户记忆评估的 Agentic RAG 系统配置

本模块提供系统配置管理，LLM 配置由项目根目录的统一配置提供。
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum
from pathlib import Path

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)


class IndexMode(str, Enum):
    """对话块的索引模式"""
    DENSE = "dense"  # 仅稠密向量
    SPARSE = "sparse"  # 仅稀疏向量 (BM25)
    HYBRID = "hybrid"  # 混合稠密和稀疏


class ChunkingStrategy(str, Enum):
    """对话分块策略"""
    FIXED_ROUNDS = "fixed_rounds"  # 每块固定轮数
    SEMANTIC = "semantic"  # 语义边界
    TIME_BASED = "time_based"  # 基于时间间隔


@dataclass
class LLMConfig:
    """LLM 配置（由项目根目录统一配置提供）

    注意：此配置类保留用于向后兼容，实际 LLM 配置由
    ai-agant 根目录的 .env 文件和 llm.client 模块管理。
    """
    provider: str = "auto"  # 自动从环境变量读取
    model: Optional[str] = None  # 自动从环境变量读取
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = True

    def get_client_config(self) -> tuple[Dict[str, Any], str]:
        """获取 OpenAI 客户端配置（兼容性方法）

        注意：新代码应使用 `from llm.client import get_llm_client`
        """
        # 返回最小配置，实际使用 get_llm_client
        return {}, "auto"


@dataclass
class ChunkingConfig:
    """对话分块配置"""
    strategy: ChunkingStrategy = ChunkingStrategy.FIXED_ROUNDS
    rounds_per_chunk: int = 20  # FIXED_ROUNDS 模式下每块的轮数
    overlap_rounds: int = 2  # 块之间的重叠轮数
    include_metadata: bool = True  # 在块中包含对话元数据
    min_chunk_size: int = 5  # 块的最小轮数
    max_chunk_size: int = 50  # 块的最大轮数


@dataclass
class IndexConfig:
    """RAG 索引配置"""
    mode: IndexMode = IndexMode.HYBRID
    embedding_model: str = "text-embedding-3-small"  # OpenAI 嵌入模型
    embedding_dim: int = 1536  # 嵌入维度
    index_path: str = "indexes/memory_index"
    chunk_store_path: str = "data/chunk_store.json"
    enable_contextual: bool = True  # 为块添加上下文信息
    contextual_window: int = 2  # 上下文轮数
    # 检索后端选择：
    #   "auto"     -> 如果可访问，使用端口 4242 的检索流水线，
    #                 否则回退到内置的、无依赖的本地 BM25 索引（完全离线工作）
    #   "local"    -> 始终使用内置的本地 BM25 索引（无需外部服务）
    #   "pipeline" -> 始终使用端口 4242 的外部检索流水线
    retrieval_backend: str = "auto"
    retrieval_url: str = "http://localhost:4242"  # 外部检索流水线端点


@dataclass
class EvaluationConfig:
    """评估框架配置"""
    test_cases_dir: str = "test_cases"
    results_dir: str = "results"
    enable_verbose: bool = True
    save_trajectories: bool = True
    max_iterations: int = 10  # ReAct 模式的最大迭代次数
    enable_caching: bool = True  # 缓存索引对话


@dataclass
class AgentConfig:
    """智能体行为配置"""
    enable_reasoning: bool = True  # 显示推理步骤
    enable_citations: bool = True  # 在响应中包含引用
    max_search_results: int = 5  # 考虑的最大搜索结果数
    confidence_threshold: float = 0.7  # 答案的最低置信度
    enable_multi_search: bool = True  # 允许每次查询多次搜索
    max_searches_per_query: int = 3  # 允许的最大搜索次数


@dataclass
class Config:
    """主配置容器"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    index: IndexConfig = field(default_factory=IndexConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)

    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量创建配置"""
        config = cls()

        # 应用环境变量覆盖
        if rounds := os.getenv("ROUNDS_PER_CHUNK"):
            config.chunking.rounds_per_chunk = int(rounds)

        if index_mode := os.getenv("INDEX_MODE"):
            config.index.mode = IndexMode(index_mode)

        if backend := os.getenv("RETRIEVAL_BACKEND"):
            config.index.retrieval_backend = backend

        if test_cases_dir := os.getenv("TEST_CASES_DIR"):
            config.evaluation.test_cases_dir = test_cases_dir

        return config

    def save(self, path: str):
        """将配置保存到 JSON 文件"""
        import json

        config_dict = {
            "llm": {
                "provider": config.llm.provider,
                "model": config.llm.model,
                "temperature": config.llm.temperature,
                "max_tokens": config.llm.max_tokens,
                "stream": config.llm.stream
            },
            "chunking": {
                "strategy": config.chunking.strategy,
                "rounds_per_chunk": config.chunking.rounds_per_chunk,
                "overlap_rounds": config.chunking.overlap_rounds,
                "include_metadata": config.chunking.include_metadata
            },
            "index": {
                "mode": config.index.mode,
                "embedding_model": config.index.embedding_model,
                "enable_contextual": config.index.enable_contextual,
                "contextual_window": config.index.contextual_window
            },
            "evaluation": {
                "enable_verbose": config.evaluation.enable_verbose,
                "save_trajectories": config.evaluation.save_trajectories,
                "max_iterations": config.evaluation.max_iterations
            },
            "agent": {
                "enable_reasoning": config.agent.enable_reasoning,
                "enable_citations": config.agent.enable_citations,
                "max_search_results": config.agent.max_search_results,
                "confidence_threshold": config.agent.confidence_threshold
            }
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "Config":
        """从 JSON 文件加载配置"""
        import json

        with open(path, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)

        config = cls()

        # 更新 LLM 配置
        if "llm" in config_dict:
            for key, value in config_dict["llm"].items():
                setattr(config.llm, key, value)

        # 更新其他配置
        for section in ["chunking", "index", "evaluation", "agent"]:
            if section in config_dict:
                section_config = getattr(config, section)
                for key, value in config_dict[section].items():
                    # 处理枚举
                    if key == "strategy" and section == "chunking":
                        value = ChunkingStrategy(value)
                    elif key == "mode" and section == "index":
                        value = IndexMode(value)
                    setattr(section_config, key, value)

        return config
