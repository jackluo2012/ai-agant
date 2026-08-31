"""固定版本 Generative Agents 上游源码的运行时配置遮蔽层。

上游项目要求用户把明文 API 密钥写进它的 ``utils.py``。实验 10-5 改为：
本遮蔽层借助 ``compat/`` 在导入路径上排在上游源码之前，使上游的
``import utils`` 命中本文件；所有凭据一律从项目根目录统一的 ``.env``
配置读取（经 ``llm.client`` 封装加载），本目录内不存放任何密钥。
"""

from __future__ import annotations

import os
import sys

# 添加项目根目录到路径，确保可以导入统一的 LLM 封装模块
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from llm.client import get_llm_client

# 统一 LLM 配置：密钥、端点与模型名全部来自项目根目录 .env
# （get_llm_client 同时完成配置校验，缺失配置会直接报错）
_client = get_llm_client()

openai_api_key = _client.api_key or ""
openai_api_base = str(_client.base_url or "")
key_owner = "ai-agant 实验 10-5"

# 以下为上游 utils.py 的路径配置，改由环境变量注入（由 run_campaign 设置）
maze_assets_loc = os.environ["GA_MAZE_ASSETS_ROOT"]
env_matrix = f"{maze_assets_loc}/the_ville/matrix"
env_visuals = f"{maze_assets_loc}/the_ville/visuals"

fs_storage = os.environ["GA_STORAGE_ROOT"]
fs_temp_storage = os.environ["GA_TEMP_STORAGE_ROOT"]

collision_block_id = "32125"
debug = False
