from __future__ import annotations

import sys
from pathlib import Path


# 把项目目录加入导入路径，保证测试可以无需安装直接导入各模块
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
