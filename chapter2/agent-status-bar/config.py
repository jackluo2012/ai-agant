"""
状态栏 Agent 配置模块
=====================

提供配置管理功能，支持从环境变量和预设加载配置。
"""

import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()


@dataclass
class AgentConfig:
    """状态栏 Agent 的配置类"""

    # ===== API 配置 =====
    api_key: Optional[str] = None           # API 密钥
    provider: str = "kimi"                 # LLM 提供商
    model: Optional[str] = None            # 模型名称
    base_url: Optional[str] = None         # API 基础 URL（可选）

    # ===== 系统提示功能开关 =====
    enable_timestamps: bool = True         # 启用时间戳跟踪
    enable_tool_counter: bool = True       # 启用工具调用计数器
    enable_todo_list: bool = True          # 启用 TODO 列表管理
    enable_detailed_errors: bool = True    # 启用详细错误信息
    enable_system_state: bool = True       # 启用系统状态感知

    # ===== 格式化选项 =====
    timestamp_format: str = "%Y-%m-%d %H:%M:%S"  # 时间戳格式
    simulate_time_delay: bool = False            # 模拟时间延迟（演示用）

    # ===== 执行选项 =====
    max_iterations: int = 20               # 最大迭代次数
    verbose: bool = False                  # 详细日志输出
    timeout: int = 30                      # 命令执行超时（秒）

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """
        从环境变量创建配置

        Returns:
            从环境变量加载的 AgentConfig 实例
        """
        return cls(
            api_key=os.getenv("API_KEY") or os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY") or os.getenv("OPENAI_API_KEY"),
            provider=os.getenv("LLM_PROVIDER", "kimi"),
            model=os.getenv("LLM_MODEL"),
            base_url=os.getenv("BASE_URL"),
            enable_timestamps=os.getenv("ENABLE_TIMESTAMPS", "true").lower() == "true",
            enable_tool_counter=os.getenv("ENABLE_TOOL_COUNTER", "true").lower() == "true",
            enable_todo_list=os.getenv("ENABLE_TODO_LIST", "true").lower() == "true",
            enable_detailed_errors=os.getenv("ENABLE_DETAILED_ERRORS", "true").lower() == "true",
            enable_system_state=os.getenv("ENABLE_SYSTEM_STATE", "true").lower() == "true",
            timestamp_format=os.getenv("TIMESTAMP_FORMAT", "%Y-%m-%d %H:%M:%S"),
            simulate_time_delay=os.getenv("SIMULATE_TIME_DELAY", "false").lower() == "true",
            max_iterations=int(os.getenv("MAX_ITERATIONS", "20")),
            verbose=os.getenv("VERBOSE", "false").lower() == "true",
            timeout=int(os.getenv("COMMAND_TIMEOUT", "30"))
        )

    def validate(self) -> bool:
        """
        验证配置

        Returns:
            验证通过返回 True

        Raises:
            ValueError: 当配置无效时
        """
        if not self.api_key:
            raise ValueError("需要 API 密钥。请设置 KIMI_API_KEY 或 MOONSHOT_API_KEY 环境变量。")

        if self.provider not in ["kimi", "moonshot"]:
            raise ValueError(f"不支持的提供商: {self.provider}")

        if self.max_iterations < 1:
            raise ValueError("max_iterations 必须至少为 1")

        if self.timeout < 1:
            raise ValueError("timeout 必须至少为 1 秒")

        return True


# ===== 配置预设 =====

PRESETS = {
    # 完整功能：所有状态栏技术都启用
    "full": AgentConfig(
        enable_timestamps=True,
        enable_tool_counter=True,
        enable_todo_list=True,
        enable_detailed_errors=True,
        enable_system_state=True
    ),

    # 最小配置：所有状态栏技术都禁用
    "minimal": AgentConfig(
        enable_timestamps=False,
        enable_tool_counter=False,
        enable_todo_list=False,
        enable_detailed_errors=False,
        enable_system_state=False
    ),

    # 调试模式：所有功能启用 + 详细日志
    "debug": AgentConfig(
        enable_timestamps=True,
        enable_tool_counter=True,
        enable_todo_list=True,
        enable_detailed_errors=True,
        enable_system_state=True,
        verbose=True
    ),

    # 演示模式：所有功能启用 + 时间模拟
    "demo": AgentConfig(
        enable_timestamps=True,
        enable_tool_counter=True,
        enable_todo_list=True,
        enable_detailed_errors=True,
        enable_system_state=True,
        simulate_time_delay=True
    )
}


def get_config(preset: Optional[str] = None) -> AgentConfig:
    """
    从环境变量或预设获取配置

    Args:
        preset: 可选的预设名称 ('full', 'minimal', 'debug', 'demo')

    Returns:
        AgentConfig 实例
    """
    if preset and preset in PRESETS:
        config = PRESETS[preset]
        # 如果环境变量中有 API 密钥，则覆盖
        config.api_key = os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY")
        return config

    return AgentConfig.from_env()
