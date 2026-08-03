"""
用户记忆系统配置模块
"""

import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from enum import Enum

# 加载环境变量
load_dotenv()


class MemoryMode(Enum):
    """记忆管理模式"""
    NOTES = "notes"  # 简单笔记/事实（基础）
    ENHANCED_NOTES = "enhanced_notes"  # 增强笔记，包含完整上下文的段落
    JSON_CARDS = "json_cards"  # 层次化 JSON 记忆卡片（基础）
    ADVANCED_JSON_CARDS = "advanced_json_cards"  # 高级 JSON 卡片，包含完整卡片对象


class Config:
    """用户记忆系统配置设置"""

    # 记忆配置
    MEMORY_MODE: MemoryMode = MemoryMode(os.getenv("MEMORY_MODE", "notes").lower())
    MAX_MEMORY_ITEMS: int = int(os.getenv("MAX_MEMORY_ITEMS", "100"))
    MEMORY_UPDATE_TEMPERATURE: float = float(os.getenv("MEMORY_UPDATE_TEMPERATURE", "0.2"))

    # Dify 配置（用于对话历史搜索）
    DIFY_API_KEY: str = os.getenv("DIFY_API_KEY", "")
    DIFY_BASE_URL: str = os.getenv("DIFY_BASE_URL", "https://api.dify.ai/v1")
    DIFY_DATASET_ID: str = os.getenv("DIFY_DATASET_ID", "")
    ENABLE_HISTORY_SEARCH: bool = os.getenv("ENABLE_HISTORY_SEARCH", "false").lower() == "true"

    # 会话配置
    SESSION_TIMEOUT: int = int(os.getenv("SESSION_TIMEOUT", "3600"))  # 秒
    MAX_CONTEXT_LENGTH: int = int(os.getenv("MAX_CONTEXT_LENGTH", "8000"))  # tokens

    # LOCOMO 基准测试配置
    LOCOMO_DATASET_PATH: str = os.getenv("LOCOMO_DATASET_PATH", "data/locomo")
    LOCOMO_OUTPUT_DIR: str = os.getenv("LOCOMO_OUTPUT_DIR", "results/locomo")

    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: Optional[str] = os.getenv("LOG_FILE", "logs/user_memory.log")
    LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

    # 存储路径
    MEMORY_STORAGE_DIR: str = os.getenv("MEMORY_STORAGE_DIR", "data/memories")
    CONVERSATION_HISTORY_DIR: str = os.getenv("CONVERSATION_HISTORY_DIR", "data/conversations")

    @classmethod
    def create_directories(cls):
        """创建必要的目录（如果不存在）"""
        os.makedirs(cls.MEMORY_STORAGE_DIR, exist_ok=True)
        os.makedirs(cls.CONVERSATION_HISTORY_DIR, exist_ok=True)
        os.makedirs(cls.LOCOMO_OUTPUT_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(cls.LOG_FILE) or "logs", exist_ok=True)

    @classmethod
    def print_config(cls):
        """打印当前配置（隐藏敏感数据）"""
        print("\n" + "="*50)
        print("用户记忆系统配置")
        print("="*50)
        print(f"记忆模式: {cls.MEMORY_MODE.value}")
        print(f"最大记忆项: {cls.MAX_MEMORY_ITEMS}")
        print(f"历史搜索: {'已启用' if cls.ENABLE_HISTORY_SEARCH else '已禁'}")

        # 显示哪些 API keys 已设置
        print(f"\nAPI Keys:")
        print(f"  Dify: {'✓ 已设置' if cls.DIFY_API_KEY else '✗ 未设置'}")

        print(f"\n日志级别: {cls.LOG_LEVEL}")
        print("="*50 + "\n")
