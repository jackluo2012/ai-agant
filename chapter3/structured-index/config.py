"""
结构化索引项目配置
==================

包含 RAPTOR 和 GraphRAG 的项目特定配置。
LLM 配置由项目根目录的 .env 和 llm.client 模块统一管理。
"""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class RaptorConfig:
    """RAPTOR 层次树索引配置"""
    # 索引参数
    chunk_size: int = 1000           # 每个分块的词数
    chunk_overlap: int = 200         # 分块之间的重叠词数
    tree_depth: int = 3              # 树的最大深度
    summarization_length: int = 200 # 摘要的词数

    # 模型参数（从 .env 读取，这里仅作默认值）
    max_tokens: int = 2048
    temperature: float = 0.1

    # 路径配置
    index_dir: Path = Path("indexes/raptor")


@dataclass
class GraphRAGConfig:
    """GraphRAG 知识图谱索引配置"""
    # 索引参数
    chunk_size: int = 1200              # 每个分块的词数
    chunk_overlap: int = 100            # 分块之间的重叠词数
    max_knowledge_triples: int = 10     # 每个分块提取的最大知识三元组数

    # 社区检测配置
    community_detection_algorithm: str = "leiden"  # leiden 或 louvain

    # 模型参数（从 .env 读取，这里仅作默认值）
    temperature: float = 0.1

    # 路径配置
    index_dir: Path = Path("indexes/graphrag")
    cache_dir: Path = Path("cache/graphrag")


@dataclass
class APIConfig:
    """HTTP API 服务配置"""
    host: str = "127.0.0.1"
    port: int = 4242
    reload: bool = True
    max_results: int = 10
    timeout_seconds: int = 30


def get_raptor_config() -> RaptorConfig:
    """从环境变量获取 RAPTOR 配置"""
    return RaptorConfig(
        chunk_size=int(os.getenv("RAPTOR_CHUNK_SIZE", "1000")),
        chunk_overlap=int(os.getenv("RAPTOR_CHUNK_OVERLAP", "200")),
        tree_depth=int(os.getenv("RAPTOR_TREE_DEPTH", "3")),
        summarization_length=int(os.getenv("RAPTOR_SUMMARY_LENGTH", "200")),
        max_tokens=int(os.getenv("RAPTOR_MAX_TOKENS", "2048")),
        temperature=float(os.getenv("RAPTOR_TEMPERATURE", "0.1")),
    )


def get_graphrag_config() -> GraphRAGConfig:
    """从环境变量获取 GraphRAG 配置"""
    return GraphRAGConfig(
        chunk_size=int(os.getenv("GRAPHRAG_CHUNK_SIZE", "1200")),
        chunk_overlap=int(os.getenv("GRAPHRAG_CHUNK_OVERLAP", "100")),
        max_knowledge_triples=int(os.getenv("GRAPHRAG_MAX_TRIPLES", "10")),
        community_detection_algorithm=os.getenv("GRAPHRAG_COMMUNITY_ALG", "leiden"),
        temperature=float(os.getenv("GRAPHRAG_TEMPERATURE", "0.1")),
    )


def get_api_config() -> APIConfig:
    """从环境变量获取 API 配置"""
    return APIConfig(
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "4242")),
        reload=os.getenv("API_RELOAD", "true").lower() == "true",
        max_results=int(os.getenv("API_MAX_RESULTS", "10")),
        timeout_seconds=int(os.getenv("API_TIMEOUT", "30"))
    )
