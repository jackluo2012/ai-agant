"""
执行工具 MCP 服务器配置管理

本配置文件包含项目特定的配置项（安全设置、工作区等）。
LLM 相关配置由项目根目录的 .env 文件统一管理。
"""

import os
import sys
from pathlib import Path
from typing import Optional


def _env_int(name: str, default: int) -> int:
    """
    读取整数环境变量，如果格式错误则回退到默认值（并发出警告）

    Args:
        name: 环境变量名称
        default: 默认值

    Returns:
        环境变量的整数值或默认值
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"警告：无效的 {name}={raw!r}（必须是整数）；使用默认值 {default}",
              file=sys.stderr)
        return default


def _env_float(name: str, default: float) -> float:
    """
    读取浮点数环境变量，如果格式错误则回退到默认值（并发出警告）

    Args:
        name: 环境变量名称
        default: 默认值

    Returns:
        环境变量的浮点数值或默认值
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"警告：无效的 {name}={raw!r}（必须是数字）；使用默认值 {default}",
              file=sys.stderr)
        return default


class Config:
    """MCP 服务器配置类"""

    # 模型参数（可选，使用项目根目录 .env 中的配置）
    TEMPERATURE: float = _env_float("TEMPERATURE", 0.7)
    MAX_TOKENS: int = _env_int("MAX_TOKENS", 4096)

    # 外部服务配置
    GOOGLE_CALENDAR_CREDENTIALS_FILE: str = os.getenv(
        "GOOGLE_CALENDAR_CREDENTIALS_FILE",
        "credentials.json"
    )
    GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN")

    # 安全设置
    REQUIRE_APPROVAL_FOR_DANGEROUS_OPS: bool = (
        os.getenv("REQUIRE_APPROVAL_FOR_DANGEROUS_OPS", "true").lower() == "true"
    )
    AUTO_SUMMARIZE_COMPLEX_OUTPUT: bool = (
        os.getenv("AUTO_SUMMARIZE_COMPLEX_OUTPUT", "true").lower() == "true"
    )
    AUTO_VERIFY_CODE: bool = (
        os.getenv("AUTO_VERIFY_CODE", "true").lower() == "true"
    )
    MAX_OUTPUT_LENGTH: int = _env_int("MAX_OUTPUT_LENGTH", 1000)

    # 工作区配置
    WORKSPACE_DIR: Path = Path(os.getenv("WORKSPACE_DIR", os.getcwd()))
