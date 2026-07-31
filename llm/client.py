"""
通用 LLM 客户端
==================

提供统一的 LLM 接口，支持任意兼容 OpenAI API 格式的提供商。

使用方法:
    from llm.client import get_llm_client

    client = get_llm_client()
    response = client.chat.completions.create(...)
"""

import os
import logging
from typing import Optional, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env_path = os.path.join(_project_root, '.env')
load_dotenv(_env_path)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# 预设提供商配置
PROVIDER_CONFIGS = {
    'kimi': {
        'base_url': 'https://api.moonshot.cn/v1',
        'default_model': 'kimi-k3'
    },
    'moonshot': {
        'base_url': 'https://api.moonshot.cn/v1',
        'default_model': 'kimi-k3'
    },
    'openai': {
        'base_url': 'https://api.openai.com/v1',
        'default_model': 'gpt-4o'
    },
    'deepseek': {
        'base_url': 'https://api.deepseek.com',
        'default_model': 'deepseek-chat'
    },
    'anthropic': {
        'base_url': 'https://api.anthropic.com/v1',
        'default_model': 'claude-sonnet-4-20250514'
    },
    'aliyun': {
        'base_url': None,  # 需要 BASE_URL 环境变量
        'default_model': None
    },
    'custom': {
        'base_url': None,  # 需要 BASE_URL 环境变量
        'default_model': None
    }
}


def _get_env_config() -> Dict[str, Optional[str]]:
    """
    从环境变量获取 LLM 配置

    Returns:
        包含 api_key, provider, model, base_url 的字典
    """
    # 获取 API 密钥
    api_key = (
        os.getenv("API_KEY") or
        os.getenv("KIMI_API_KEY") or
        os.getenv("MOONSHOT_API_KEY") or
        os.getenv("OPENAI_API_KEY") or
        os.getenv("DEEPSEEK_API_KEY") or
        os.getenv("ANTHROPIC_API_KEY")
    )

    # 获取提供商
    provider = os.getenv("LLM_PROVIDER", "kimi").lower()

    # 获取模型
    model = os.getenv("LLM_MODEL")

    # 获取基础 URL
    base_url = os.getenv("BASE_URL")

    return {
        'api_key': api_key,
        'provider': provider,
        'model': model,
        'base_url': base_url
    }


def get_llm_client(
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None
) -> OpenAI:
    """
    获取配置好的 LLM 客户端

    Args:
        api_key: API 密钥（可选，优先级最高）
        provider: 提供商名称（可选）
        model: 模型名称（可选）
        base_url: API 基础 URL（可选）

    Returns:
        配置好的 OpenAI 客户端实例

    Raises:
        ValueError: 当缺少必要配置时

    环境变量:
        API_KEY: 通用 API 密钥
        LLM_PROVIDER: 提供商名称
        LLM_MODEL: 模型名称
        BASE_URL: API 基础 URL

    示例:
        # 方式一：使用环境变量配置（推荐）
        client = get_llm_client()

        # 方式二：代码中指定配置
        client = get_llm_client(
            api_key="your-key",
            provider="openai",
            model="gpt-4o"
        )

        # 方式三：自定义提供商
        client = get_llm_client(
            api_key="your-key",
            provider="custom",
            base_url="https://your-api.com/v1",
            model="your-model"
        )
    """
    # 从环境变量获取默认配置
    env_config = _get_env_config()

    # 参数覆盖环境变量
    api_key = api_key or env_config['api_key']
    provider = (provider or env_config['provider']).lower()
    model = model or env_config['model']
    base_url = base_url or env_config['base_url']

    # 验证 API 密钥
    if not api_key:
        raise ValueError(
            "API 密钥未设置。请通过以下方式之一设置：\n"
            "1. 环境变量: export API_KEY='your-key'\n"
            "2. .env 文件: API_KEY=your-key\n"
            "3. 函数参数: get_llm_client(api_key='your-key')"
        )

    # 解析提供商配置
    if provider in PROVIDER_CONFIGS:
        provider_config = PROVIDER_CONFIGS[provider]
        resolved_base_url = base_url or provider_config['base_url']
        default_model = provider_config['default_model']
    else:
        # 未知提供商视为自定义
        resolved_base_url = base_url
        default_model = None
        logger.warning(f"未知提供商 '{provider}'，视为自定义提供商")

    # 验证基础 URL
    if not resolved_base_url:
        raise ValueError(
            f"提供商 '{provider}' 需要指定 BASE_URL。\n"
            f"请通过以下方式之一设置：\n"
            f"1. 环境变量: export BASE_URL='https://...'\n"
            f"2. .env 文件: BASE_URL=https://...\n"
            f"3. 函数参数: get_llm_client(base_url='https://...')"
        )

    # 确定模型
    resolved_model = model or default_model
    if not resolved_model:
        raise ValueError(
            f"请提供模型名称。\n"
            f"提供商 '{provider}' 没有默认模型。\n"
            f"请通过以下方式之一设置：\n"
            f"1. 环境变量: export LLM_MODEL='your-model'\n"
            f"2. 函数参数: get_llm_client(model='your-model')"
        )

    # 创建客户端
    client = OpenAI(api_key=api_key, base_url=resolved_base_url)

    logger.info(f"LLM 客户端已初始化: provider={provider}, model={resolved_model}, api={resolved_base_url}")

    # 将配置信息附加到客户端对象，方便后续使用
    client.provider = provider
    client.model_name = resolved_model
    client.base_url = resolved_base_url

    return client


def get_llm_config() -> Dict[str, Any]:
    """
    获取当前 LLM 配置信息

    Returns:
        包含当前配置的字典
    """
    env_config = _get_env_config()

    provider = env_config['provider'].lower()
    if provider in PROVIDER_CONFIGS:
        provider_config = PROVIDER_CONFIGS[provider]
        base_url = env_config['base_url'] or provider_config['base_url']
        default_model = provider_config['default_model']
    else:
        base_url = env_config['base_url']
        default_model = None

    return {
        'provider': provider,
        'model': env_config['model'] or default_model,
        'base_url': base_url,
        'api_key_configured': bool(env_config['api_key'])
    }


def print_config():
    """打印当前 LLM 配置（用于调试）"""
    config = get_llm_config()

    print("\n" + "="*60)
    print("  当前 LLM 配置")
    print("="*60)
    print(f"提供商: {config['provider']}")
    print(f"模型: {config['model'] or '未配置'}")
    print(f"API 地址: {config['base_url'] or '未配置'}")
    print(f"API 密钥: {'已配置' if config['api_key_configured'] else '未配置'}")
    print("="*60 + "\n")


# 导出
__all__ = ['get_llm_client', 'get_llm_config', 'print_config']
