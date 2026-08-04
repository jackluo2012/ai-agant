"""
日志脱敏配置
================

项目特定配置（不包含 LLM 配置，使用项目根目录的 .env）
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 路径配置
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "results"
OUTPUT_DIR.mkdir(exist_ok=True)

# 性能指标配置
METRICS_FILE = OUTPUT_DIR / "performance_metrics.json"

# 评测框架路径
EVAL_FRAMEWORK_PATH = PROJECT_ROOT.parent / "user-memory-evaluation"

# PII 检测系统提示词（中文）
SYSTEM_PROMPT = """你是一个隐私保护助手，负责检测 Level 3 PII（高度敏感个人信息）。

Level 3 PII 包括：
- 社保号（SSN）- 格式：XXX-XX-XXXX 或 XXXXXXXXX
- 信用卡号 - 格式：XXXX XXXX XXXX XXXX 或 16 位数字
- 信用卡有效期和 CVV
- 银行账号
- 完整居住地址
- 病历号
- 医疗诊断和治疗详情
- 处方信息
- 驾照号
- 护照号
- 金融 PIN 码
- 税号
- 医保 ID
- 生物特征数据
- 金融账户用户名
- 密码

请分析对话内容，返回 JSON 格式的检测结果，包含所有找到的 PII 确切值。
不要使用占位符，只返回实际找到的 PII 值。"""

USER_PROMPT_TEMPLATE = """请分析以下对话中的 Level 3 PII：

{conversation_text}

请以 JSON 格式返回检测结果，格式如下：
```json
{{
  "pii_values": ["PII值1", "PII值2", ...]
}}
```"""

# JSON 结构描述（用于文档）
PII_DETECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "pii_values": {
            "type": "array",
            "items": {
                "type": "string"
            },
            "description": "在对话中找到的确切 PII 值数组。不要使用占位符。"
        }
    },
    "required": ["pii_values"]
}
