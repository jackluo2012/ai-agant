"""
Configuration for LLM Tool Calling Demo
支持 llama.cpp 和 vLLM 两种后端
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================================
# llama.cpp Server Configuration - 主要配置
# ============================================================================
LLAMA_HOST = os.getenv("LLAMA_HOST", "192.168.1.158")
LLAMA_PORT = int(os.getenv("LLAMA_PORT", 11434))
LLAMA_MODEL = os.getenv("MODEL_NAME", "MiniCPM5-1B-Q4_K_M.gguf")

# llama.cpp 服务器完整 URL
LLAMA_BASE_URL = f"http://{LLAMA_HOST}:{LLAMA_PORT}"
LLAMA_OPENAI_COMPATIBLE_URL = f"{LLAMA_BASE_URL}/v1"

# ============================================================================
# vLLM Configuration - 可选配置
# ============================================================================
VLLM_MODEL_NAME = os.getenv("VLLM_MODEL_NAME", "Qwen/Qwen3-0.6B")
VLLM_MODEL_PATH = os.getenv("VLLM_MODEL_PATH", None)
VLLM_PORT = int(os.getenv("VLLM_PORT", 8000))
VLLM_HOST = os.getenv("VLLM_HOST", "localhost")

# vLLM Server Configuration
VLLM_SERVER_CONFIG = {
    "model": VLLM_MODEL_NAME,
    "port": VLLM_PORT,
    "host": VLLM_HOST,
    "enable_auto_tool_choice": True,
    "tool_call_parser": "hermes",
    "chat_template": "tool_use",
    "max_model_len": 8192,
    "gpu_memory_utilization": 0.9,
    "dtype": "auto",
    "enforce_eager": False,
}

# OpenAI Client Configuration (for connecting to vLLM)
OPENAI_API_BASE = f"http://{VLLM_HOST}:{VLLM_PORT}/v1"
OPENAI_API_KEY = "EMPTY"

# ============================================================================
# Tool Configuration
# ============================================================================
ENABLE_WEATHER_TOOL = True
ENABLE_CALCULATOR_TOOL = True
ENABLE_SEARCH_TOOL = True

# ============================================================================
# Logging
# ============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = Path("logs") / "llm_tool_demo.log"

# ============================================================================
# 使用说明
# ============================================================================
"""
本项目支持两种后端：

1. llama.cpp - 默认配置
   - 模型: MiniCPM5-1B-Q4_K_M.gguf
   - 服务器地址: 通过 .env 文件配置 LLAMA_HOST 和 LLAMA_PORT
   - 使用方式: 参考 ollama_native.py (使用 OpenAI 兼容 API)

2. vLLM - 可选配置
   - 模型: Qwen/Qwen3-0.6B
   - 服务器地址: 通过 VLLM_HOST 和 VLLM_PORT 配置
   - 使用方式: 参考 server.py 和 main.py

快速开始:
1. 复制 .env.example 到 .env
2. 修改 LLAMA_HOST 为你的 llama.cpp 服务器 IP 地址
3. 运行: python ollama_native.py
"""
