"""Agentic RAG 系统配置

本配置文件仅包含知识库和 Agent 特定配置。
LLM 配置统一使用项目根目录的 .env 文件和 llm.client 模块。
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class KnowledgeBaseType(str, Enum):
    """知识库后端类型"""
    OFFLINE = "offline"  # 内置离线 BM25（无需服务器/API）
    LOCAL = "local"      # 本地检索流水线
    DIFY = "dify"        # Dify 知识库 API


@dataclass
class KnowledgeBaseConfig:
    """知识库配置"""
    type: KnowledgeBaseType = KnowledgeBaseType.LOCAL

    # 离线 BM25 后端配置（无外部服务器/API）
    offline_corpus_path: str = "laws"
    offline_top_k: int = 5

    # 本地检索流水线配置
    local_base_url: str = "http://localhost:4242"
    local_top_k: int = 3

    # Dify 配置
    dify_api_key: Optional[str] = field(default_factory=lambda: os.getenv("DIFY_API_KEY"))
    dify_base_url: str = "https://api.dify.ai/v1"
    dify_dataset_id: Optional[str] = None
    dify_top_k: int = 3

    # 文档存储
    document_store_path: str = "document_store.json"


@dataclass
class ChunkingConfig:
    """文档分块配置"""
    chunk_size: int = 2048           # 每块字符数
    max_chunk_size: int = 1024       # 段落边界时的最大块大小
    chunk_overlap: int = 200         # 块之间重叠
    respect_paragraph_boundary: bool = True
    min_chunk_size: int = 100         # 最小块大小


@dataclass
class AgentConfig:
    """Agent 配置"""
    max_iterations: int = 10               # 最大推理迭代次数
    enable_reasoning_trace: bool = True    # 启用推理轨迹
    enable_citations: bool = True          # 启用引用
    strict_knowledge_base: bool = True     # 仅从知识库回答
    conversation_history_limit: int = 20    # 保留的最大对话轮数
    verbose: bool = True                    # 详细日志


@dataclass
class EvaluationConfig:
    """评估配置"""
    dataset_path: str = "evaluation/legal_qa_dataset.json"
    results_path: str = "evaluation/results"
    metrics: list = field(default_factory=lambda: ["accuracy", "relevance", "citation_quality"])


@dataclass
class Config:
    """主配置"""
    knowledge_base: KnowledgeBaseConfig = field(default_factory=KnowledgeBaseConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)

    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量创建配置"""
        config = cls()

        # 从环境变量覆盖知识库类型
        if kb_type := os.getenv("KB_TYPE"):
            config.knowledge_base.type = KnowledgeBaseType(kb_type.lower())

        return config
