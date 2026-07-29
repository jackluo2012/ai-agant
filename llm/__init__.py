"""
LLM 通用封装模块
================

提供统一的大模型接口，支持任意兼容 OpenAI API 格式的提供商。

快速开始:
    from llm.client import get_llm_client

    client = get_llm_client()
    response = client.chat.completions.create(
        model=client.model_name,
        messages=[{"role": "user", "content": "你好"}]
    )

配置方式:
    1. 环境变量（推荐）:
       export API_KEY='your-key'
       export LLM_PROVIDER='openai'
       export LLM_MODEL='gpt-4o'
       export BASE_URL='https://...'

    2. .env 文件:
       在项目根目录的 .env 文件中配置

    3. 代码中指定:
       client = get_llm_client(api_key="...", provider="openai")

支持的提供商:
    - kimi / moonshot
    - openai
    - deepseek
    - anthropic
    - aliyun (需要配置 BASE_URL)
    - custom (任意兼容 OpenAI API 的服务)
"""

from llm.client import get_llm_client, get_llm_config, print_config

__all__ = ['get_llm_client', 'get_llm_config', 'print_config']
