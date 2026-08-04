"""检索流水线配置模块。"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class SearchMode(str, Enum):
    """检索模式枚举。"""
    DENSE = "dense"  # 稠密检索（语义）
    SPARSE = "sparse"  # 稀疏检索（关键词）
    HYBRID = "hybrid"  # 混合检索（稠密+稀疏）

@dataclass
class ServiceConfig:
    """外部服务配置。"""
    dense_service_url: str = "http://localhost:4240"  # 稠密检索服务端口 4240
    sparse_service_url: str = "http://localhost:4241"  # 稀疏检索服务端口 4241

    @classmethod
    def from_env(cls):
        """从环境变量创建配置。"""
        dense_url = os.getenv("DENSE_SERVICE_URL", "http://localhost:4240")
        sparse_url = os.getenv("SPARSE_SERVICE_URL", "http://localhost:4241")
        return cls(dense_service_url=dense_url, sparse_service_url=sparse_url)
    
@dataclass
class RerankerConfig:
    """重排序模型配置。"""
    model_name: str = "BAAI/bge-reranker-v2-m3"  # 重排序模型名称
    device: str = "mps"  # 运行设备：mps(Mac M1/M2)、cuda(GPU)、cpu
    batch_size: int = 32  # 批处理大小
    max_length: int = 8192  # 最大序列长度（与分块硬限制匹配）
    use_fp16: bool = True  # 是否使用半精度加速推理（Mac 推荐）
    
@dataclass
class PipelineConfig:
    """检索流水线配置。"""
    services: ServiceConfig = field(default_factory=ServiceConfig)
    reranker: RerankerConfig = field(default_factory=RerankerConfig)

    # 检索设置
    default_top_k: int = 20  # 从各服务检索的候选文档数量
    rerank_top_k: int = 10  # 重排序后返回的结果数量

    # 融合设置（见 fusion.py）
    # "rrf": 倒排秩融合（仅用排名，鲁棒性强）
    # "weighted": 加权融合（min-max 归一化后加权求和）
    # "avg_rank": 传统平均排名排序（遗留方法）
    fusion_method: str = "rrf"
    rrf_k: int = 60  # RRF 平滑常数

    # 日志设置
    debug: bool = True  # 调试模式
    show_scores: bool = True  # 在响应中显示所有分数（教学用）

    # 服务器设置
    host: str = "0.0.0.0"
    port: int = 4242  # 检索流水线默认端口

    @classmethod
    def from_env(cls):
        """从环境变量创建配置。"""
        config = cls()
        if os.getenv("PIPELINE_PORT"):
            config.port = int(os.getenv("PIPELINE_PORT"))
        if os.getenv("PIPELINE_HOST"):
            config.host = os.getenv("PIPELINE_HOST")
        if os.getenv("DEBUG"):
            config.debug = os.getenv("DEBUG").lower() == "true"
        return config
