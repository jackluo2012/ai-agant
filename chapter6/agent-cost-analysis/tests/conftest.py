"""测试导入引导：为 agent-cost-analysis 实验设置 Python 路径。"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# 添加实验根目录到路径
EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
if str(EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_ROOT))
