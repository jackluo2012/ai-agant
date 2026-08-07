"""通用 OpenRouter 回退机制，用于协作工具的 LLM 客户端。

本实验中的所有 LLM 入口（子 Agent 运行、智能工具、浏览器工具）都使用兼容 OpenAI 的 API。
此辅助函数集中处理凭据解析，以便：

  1. 当 OPENAI_API_KEY 存在时，行为不变（直接使用 OpenAI，或用户设置的 OPENAI_BASE_URL/OPENAI_MODEL）。
  2. 当 OPENAI_API_KEY 不存在但 OPENROUTER_API_KEY 存在时，请求透明路由到 OpenRouter
     （base_url=https://openrouter.ai/api/v1），模型 ID 映射为 provider/model 格式。
  3. 两者均未设置时，调用者可以检测"离线"状态并回退到确定性模拟路径（不生成模型输出）。
"""

import os
import sys
from typing import Optional, Tuple

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 导入统一 LLM 客户端
try:
    from llm.client import get_llm_client
    _USE_UNIFIED_CLIENT = True
except ImportError:
    _USE_UNIFIED_CLIENT = False


def map_model_for_openrouter(model: str) -> str:
    """Map a plain model id onto OpenRouter's `provider/model` form.

    Ids already containing "/" pass through unchanged; gpt-*/o1-*/o3-*/o4-*
    become openai/…; claude-* becomes anthropic/claude-opus-4.8.
    """
    if "/" in model:
        return model
    m = model.lower()
    if m.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return f"openai/{model}"
    if m.startswith("claude-"):
        return "anthropic/claude-opus-4.8"
    if m.startswith("kimi"):
        return "moonshotai/kimi-k2.6"
    return model


def has_llm() -> bool:
    """True when at least one usable LLM credential is configured."""
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY"))


def resolve_llm(default_model: str = "gpt-5.6-luna") -> Tuple[str, Optional[str], str]:
    """解析 (api_key, base_url, model)，应用 OpenRouter 回退机制。

    Returns:
        (api_key, base_url, model) 元组

    Raises:
        RuntimeError: 当未配置任何凭据时，列出可接受的密钥
    """
    # 如果统一客户端可用，尝试从中获取配置
    if _USE_UNIFIED_CLIENT:
        try:
            # 读取环境变量
            api_key = os.getenv("API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("KIMI_API_KEY")
            provider = os.getenv("LLM_PROVIDER", "kimi").lower()
            model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL", default_model)
            base_url = os.getenv("BASE_URL") or os.getenv("OPENAI_BASE_URL")

            # 特殊处理：如果是 OpenRouter 提供商
            if provider == "openrouter":
                or_key = os.getenv("OPENROUTER_API_KEY")
                if or_key:
                    return or_key, "https://openrouter.ai/api/v1", map_model_for_openrouter(model)

            # 如果有 API 密钥，直接使用
            if api_key:
                return api_key, base_url, model

        except Exception:
            # 如果统一客户端失败，回退到原有逻辑
            pass

    # 回退到原有逻辑（兼容性）
    model = os.getenv("OPENAI_MODEL", default_model)

    or_key = os.getenv("OPENROUTER_API_KEY")
    # gpt-5.x（包括 gpt-5.6*）需要在直接 API 上进行 OpenAI 组织验证；
    # 当存在 OpenRouter 密钥时，优先通过它路由这些模型 ID。
    if or_key and model.lower().startswith("gpt-5"):
        return or_key, "https://openrouter.ai/api/v1", map_model_for_openrouter(model)

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key, os.getenv("OPENAI_BASE_URL"), model

    if or_key:
        return or_key, "https://openrouter.ai/api/v1", map_model_for_openrouter(model)

    raise RuntimeError(
        "未配置 LLM 密钥。请设置 OPENAI_API_KEY 或 OPENROUTER_API_KEY "
        "（通用回退）。"
    )
