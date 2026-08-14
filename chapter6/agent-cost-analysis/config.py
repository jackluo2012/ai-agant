"""
全局配置：模型与价格。

价格换算成本时使用「每百万 token 单价（美元）」。
默认值取自 OpenAI gpt-4o-mini 的公开定价（2024-2025）：
    - 输入        : $0.15  / 1M tokens
    - 缓存命中输入 : $0.075 / 1M tokens   （命中 prompt cache 的输入按 5 折计费）
    - 输出        : $0.60  / 1M tokens

注意：
1. 默认模型使用项目根目录 .env 配置的模型。
2. LLM 客户端使用项目统一的 llm.client 模块。
3. OpenAI 的 prompt caching 是「自动」的：当请求前缀 >= 1024 token 且与近期请求
   命中相同前缀时，usage.prompt_tokens_details.cached_tokens 会大于 0，
   这部分 token 按缓存价（更便宜）计费。本项目正是用它来真实体现 KV-cache 的节省。
"""

import sys
import os
from dataclasses import dataclass

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

# 导入统一 LLM 客户端
try:
    from llm.client import get_llm_client
    _llm_client_available = True
except ImportError:
    _llm_client_available = False

# 默认模型名称（使用项目配置）
MODEL = os.environ.get("COST_DEMO_MODEL", "gpt-4o-mini")


def make_client_and_model(model: str):
    """
    构造 LLM client 并返回 (client, 实际调用的模型名)。

    使用项目统一的 LLM 客户端封装。
    """
    if not _llm_client_available:
        raise ImportError(
            "LLM 客户端模块不可用。请确保项目根目录存在 llm/client.py "
            "并已配置 .env 文件中的 LLM 相关设置。"
        )

    client = get_llm_client()
    # 使用客户端配置的模型名称
    resolved_model = getattr(client, 'model_name', model)
    return client, resolved_model

# 每百万 token 的美元单价（默认 gpt-4o-mini）
PRICE_INPUT_PER_M = 0.15      # 普通输入
PRICE_CACHED_PER_M = 0.075    # 命中缓存的输入（gpt-4o-mini 缓存读取为输入价的 50%）
PRICE_OUTPUT_PER_M = 0.60     # 输出


@dataclass(frozen=True)
class Pricing:
    """一组每百万 token 的美元单价。"""
    input_per_m: float
    cached_per_m: float
    output_per_m: float

    def cost_usd(self, prompt_tokens: int, cached_tokens: int,
                 completion_tokens: int) -> float:
        """按 token 用量换算成本（美元）。

        prompt_tokens   : usage.prompt_tokens，包含了缓存命中的部分
        cached_tokens   : usage.prompt_tokens_details.cached_tokens，命中缓存的输入 token
        completion_tokens: usage.completion_tokens

        未命中缓存的输入 = prompt_tokens - cached_tokens，按普通输入价计费；
        命中缓存的输入按缓存价计费。
        """
        uncached_input = max(prompt_tokens - cached_tokens, 0)
        return (
            uncached_input / 1_000_000 * self.input_per_m
            + cached_tokens / 1_000_000 * self.cached_per_m
            + completion_tokens / 1_000_000 * self.output_per_m
        )


# 常见 OpenAI 模型的公开单价预设（每百万 token，美元），方便 CLI 用 --model 一键切换。
# 换更强的模型不影响 KV-cache 机制（仍要求稳定前缀 >= 1024 token）。
PRICING_PRESETS = {
    "gpt-4o-mini": Pricing(0.15, 0.075, 0.60),
    "gpt-4o":      Pricing(2.50, 1.25, 10.00),
    "gpt-4.1-mini": Pricing(0.40, 0.10, 1.60),
    "gpt-4.1":     Pricing(2.00, 0.50, 8.00),
}


def default_pricing() -> Pricing:
    """返回默认模型（config 中 MODEL）的单价；未知模型回退到模块级 PRICE_* 默认值。"""
    return PRICING_PRESETS.get(
        MODEL, Pricing(PRICE_INPUT_PER_M, PRICE_CACHED_PER_M, PRICE_OUTPUT_PER_M)
    )


def cost_usd(prompt_tokens: int, cached_tokens: int, completion_tokens: int,
             pricing: "Pricing | None" = None) -> float:
    """按 token 用量换算成本（美元）。默认用模块级单价，可传入自定义 Pricing。"""
    p = pricing or Pricing(PRICE_INPUT_PER_M, PRICE_CACHED_PER_M, PRICE_OUTPUT_PER_M)
    return p.cost_usd(prompt_tokens, cached_tokens, completion_tokens)
