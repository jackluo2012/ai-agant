"""LLM 工厂：为 browser-use 示例统一提供模型客户端。

本文件使用项目根目录的统一 LLM 配置（.env 文件），不再需要单独的 API Key 配置。
"""

import sys
import os

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from llm.client import get_llm_client
except ImportError:
    # 如果无法导入统一客户端，使用 browser-use 内置的客户端
    from browser_use import ChatOpenAI, ChatGoogle
    get_llm_client = None

from browser_use import ChatOpenAI, ChatGoogle

# 默认模型名称
DEFAULT_MODEL = "gpt-4o"


def make_llm(model: str = None):
    """
    构造 LLM 客户端（使用项目根目录 .env 配置）。

    Args:
        model: 模型名称，默认使用项目配置的模型

    Returns:
        browser-use 兼容的 LLM 客户端实例

    Raises:
        RuntimeError: 当无法获取 LLM 客户端时
    """
    model = model or DEFAULT_MODEL

    # 如果有统一客户端，使用它（但 browser-use 需要特定接口）
    # 这里我们创建 browser-use 兼容的客户端

    # 根据 model 前缀决定使用哪个客户端
    if model.startswith("gemini") or model.startswith("google"):
        return ChatGoogle(model=model)
    else:
        # 默认使用 OpenAI 兼容客户端
        # 这会从项目根目录 .env 读取 API_KEY 等配置
        return ChatOpenAI(model=model)


def get_provider_from_env() -> str:
    """
    从环境变量获取 LLM 提供商。

    Returns:
        提供商名称（kimi, openai, deepseek, anthropic 等）
    """
    # 从项目根目录 .env 读取
    return os.getenv("LLM_PROVIDER", "openai")


def get_model_from_env() -> str:
    """
    从环境变量获取模型名称。

    Returns:
        模型名称
    """
    # 从项目根目录 .env 读取
    return os.getenv("LLM_MODEL", DEFAULT_MODEL)
