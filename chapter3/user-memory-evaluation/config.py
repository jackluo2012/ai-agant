"""用户记忆评估框架配置模块。

此模块仅包含项目特定的配置，所有 LLM 相关配置已迁移到项目根目录的 .env 文件，
并通过 llm.client 模块统一管理。
"""

import os
import sys

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)


class Config:
    """评估框架的配置设置。"""

    # 评估设置
    DEFAULT_EVALUATOR: str = os.getenv("DEFAULT_EVALUATOR", "kimi")
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "60"))

    # 测试用例设置
    TEST_CASES_DIR: str = os.path.join(os.path.dirname(__file__), "test_cases")
