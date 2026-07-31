"""
上下文压缩实验配置模块
======================

本模块定义上下文压缩对比实验的配置参数。

环境变量:
    SERPER_API_KEY: Serper 搜索 API 密钥（可选，无密钥时使用模拟数据）
    MAX_ITERATIONS: 最大迭代次数（默认 50）
    MAX_WEBPAGE_LENGTH: 网页内容最大长度（默认 50000）
    SUMMARY_MAX_TOKENS: 摘要最大 token 数（默认 500）
    CONTEXT_WINDOW_SIZE: 上下文窗口大小（默认 128000）
    ENABLE_VERBOSE: 启用详细日志（默认 false）
"""

import os
import logging
from typing import Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv("/home/jackluo/my/ai-agent/ai-agant/.env")

# 配置日志
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Config:
    """上下文压缩实验配置类"""

    # ===== 搜索配置 =====
    SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "")
    SERPER_BASE_URL: str = "https://google.serper.dev"

    # ===== 模型配置 =====
    # 注意：实际 LLM 配置由 llm.client 统一管理
    # 这里只保留实验特定参数
    MODEL_TEMPERATURE: float = float(os.getenv("MODEL_TEMPERATURE", "0.3"))
    MODEL_MAX_TOKENS: int = int(os.getenv("MODEL_MAX_TOKENS", "8192"))

    # ===== Agent 配置 =====
    MAX_ITERATIONS: int = int(os.getenv("MAX_ITERATIONS", "50"))
    ENABLE_VERBOSE: bool = os.getenv("ENABLE_VERBOSE", "false").lower() == "true"

    # ===== 压缩配置 =====
    MAX_WEBPAGE_LENGTH: int = int(os.getenv("MAX_WEBPAGE_LENGTH", "50000"))
    SUMMARY_MAX_TOKENS: int = int(os.getenv("SUMMARY_MAX_TOKENS", "500"))

    # ===== 上下文窗口配置 =====
    # 128K 上下文预算用于演示压缩效果
    # (K3 支持约 1M 窗口，这里故意收紧以便观察压缩/溢出行为)
    CONTEXT_WINDOW_SIZE: int = 128000

    # ===== 文件路径 =====
    RESULTS_DIR: str = "results"
    CACHE_DIR: str = "cache"
    LOGS_DIR: str = "logs"

    @classmethod
    def validate(cls) -> bool:
        """
        验证配置有效性

        Returns:
            配置有效返回 True，否则返回 False
        """
        if not cls.SERPER_API_KEY:
            logger.warning("SERPER_API_KEY 未设置，将使用模拟数据")
            print("提示: SERPER_API_KEY 未设置，将使用模拟数据进行演示")
            print("获取免费 API Key: https://serper.dev")

        return True

    @classmethod
    def create_directories(cls):
        """创建必要的目录"""
        import os
        os.makedirs(cls.RESULTS_DIR, exist_ok=True)
        os.makedirs(cls.CACHE_DIR, exist_ok=True)
        os.makedirs(cls.LOGS_DIR, exist_ok=True)

    @classmethod
    def print_config(cls):
        """打印当前配置（隐藏敏感信息）"""
        print("\n" + "="*60)
        print("  上下文压缩实验配置")
        print("="*60)
        print(f"最大迭代次数: {cls.MAX_ITERATIONS}")
        print(f"上下文窗口: {cls.CONTEXT_WINDOW_SIZE:,} tokens")
        print(f"网页最大长度: {cls.MAX_WEBPAGE_LENGTH:,} 字符")
        print(f"摘要最大长度: {cls.SUMMARY_MAX_TOKENS} tokens")
        print(f"Serper API Key: {'已配置' if cls.SERPER_API_KEY else '未配置'}")
        print("="*60 + "\n")
