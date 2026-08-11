"""
agent.py —— 代码生成 Agent（自愈闭环的"大脑"）

职责：拿到无法解析的失败样本 + 报错，调用大语言模型，生成一个能正确解析该格式的
Python 解析函数 `def parse(line: str) -> dict | None`。支持把上一轮自动测试的
失败报告作为反馈再次生成（迭代修复）。
"""

from __future__ import annotations

import os
import sys
import re
from typing import List, Optional

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from llm.client import get_llm_client
except ImportError:
    get_llm_client = None
    print("警告：无法导入统一 LLM 客户端，请确保项目根目录 .env 文件配置正确")


# 系统提示词：日志解析器代码生成器
SYSTEM_PROMPT = """你是一个"日志解析器代码生成器"。用户会给你一批**同一种未知格式**的日志样本，
以及现有系统解析失败的报错。你的任务：编写一个 Python 函数，把这种格式的每一行解析成结构化字段。

严格要求：
1. 只输出一个 Python 代码块（```python ... ```），不要任何解释文字。
2. 代码块里必须定义一个函数：def parse(line: str) -> dict | None
   - 输入是一行日志（字符串）。
   - 如果这行符合你要解析的格式，返回一个 dict，键为字段名（英文小写下划线），值为解析出的内容。
   - 如果这行**不符合**这种格式，必须返回 None（不要抛异常，把机会让给其它解析器）。
3. 只能使用 Python 标准库（re、json、datetime 等），不要 import 第三方库。
4. 不要有任何 print、input、文件读写、网络访问等副作用。
5. 必须解析出用户指定的**所有必需字段**（required_keys），字段值不能为空。
6. 尽量健壮：用正则/分隔符解析，容忍字段顺序内的空格。
"""


def _build_user_prompt(
    samples: List[str],
    required_keys: List[str],
    error_report: str,
    feedback: Optional[str],
) -> str:
    """
    构建用户提示词

    Args:
        samples: 失败的日志样本列表
        required_keys: 必需解析出的字段列表
        error_report: 系统报错信息
        feedback: 上一轮测试的反馈（可选）

    Returns:
        完整的用户提示词字符串
    """
    sample_block = "\n".join(samples)
    parts = [
        "现有系统无法解析下面这种格式的日志，请生成解析函数。",
        "",
        "【失败样本（同一种新格式）】",
        sample_block,
        "",
        f"【系统报错】\n{error_report}",
        "",
        f"【必需解析出的字段 required_keys】\n{required_keys}",
    ]
    if feedback:
        parts += [
            "",
            "【上一版代码没通过自动测试，请修复后重新生成】",
            feedback,
        ]
    return "\n".join(parts)


def _extract_code(text: str) -> str:
    """
    从模型回复中抽取 Python 代码块

    Args:
        text: 模型返回的原始文本

    Returns:
        提取出的 Python 代码（没有围栏）
    """
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    return (m.group(1) if m else text).strip()


class CodeGenAgent:
    """代码生成 Agent：使用 LLM 生成日志解析器代码"""

    def __init__(self, model: Optional[str] = None):
        """
        初始化代码生成 Agent

        Args:
            model: 指定使用的模型名称（可选，默认使用项目配置的模型）
        """
        if get_llm_client is None:
            raise SystemExit("错误：无法导入 LLM 客户端，请检查项目根目录 .env 配置")

        # 获取统一 LLM 客户端
        self.client = get_llm_client()
        self.model = model or self.client.model_name

    def generate_parser_code(
        self,
        samples: List[str],
        required_keys: List[str],
        error_report: str,
        feedback: Optional[str] = None,
    ) -> str:
        """
        调用 LLM 生成解析器代码

        Args:
            samples: 失败的日志样本列表
            required_keys: 必需解析出的字段列表
            error_report: 系统报错信息
            feedback: 上一轮测试的反馈（可选）

        Returns:
            生成的 Python 源码字符串
        """
        user_prompt = _build_user_prompt(samples, required_keys, error_report, feedback)

        # 推理模型不接受 temperature=0
        _reasoning = any(k in (self.model or "").lower()
                         for k in ("gpt-5", "o1", "o3", "o4", "thinking", "reasoner", "kimi-k3"))

        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=1 if _reasoning else 0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return _extract_code(resp.choices[0].message.content or "")


# ---------------------------------------------------------------------------
# 离线（无 API）代码生成 Agent
# ---------------------------------------------------------------------------
# 与 CodeGenAgent 接口完全一致，但不调用 LLM，而是根据必需字段返回**预置**的
# 解析器源码。它的用途是：在没有 API Key 的环境里，仍能确定性地演示与验证整条
# 机制——失败检测 → （预置）生成代码 → 自动测试 → 热加载注册 → 持久化复用。
# 注意：这里的"生成"是查表返回预写好的代码，并非真正让 LLM 现写；只有换用
# CodeGenAgent 才是真正的代码生成。

# 预置的解析器代码模板
_CANNED_PARSERS = {
    # 竖线分隔格式：时间戳|级别|模块|step=N|消息
    frozenset(["timestamp", "level", "module", "step", "message"]): '''import re


def parse(line: str) -> dict | None:
    """
    解析竖线分隔格式的日志

    格式：时间戳|级别|模块|step=N|消息

    Args:
        line: 一行日志字符串

    Returns:
        解析出的字段字典，或 None（格式不匹配时）
    """
    pattern = (
        r"^(?P<timestamp>\\S+)\\|(?P<level>\\S+)\\|(?P<module>\\S+)"
        r"\\|step=(?P<step>\\d+)\\|(?P<message>.+)$"
    )
    match = re.match(pattern, line.strip())
    if match:
        return match.groupdict()
    return None
''',
    # 嵌套括号格式：[时间] (级别) <tool=名字> {k=v k=v} :: 消息
    frozenset(["timestamp", "level", "tool", "message"]): '''import re


def parse(line: str) -> dict | None:
    """
    解析嵌套括号格式的日志

    格式：[时间] (级别) <tool=名字> {k=v k=v} :: 消息

    Args:
        line: 一行日志字符串

    Returns:
        解析出的字段字典，或 None（格式不匹配时）
    """
    pattern = (
        r"\\[(?P<timestamp>.*?)\\] \\((?P<level>.*?)\\) <tool=(?P<tool>.*?)> "
        r"\\{latency_ms=(?P<latency_ms>\\d+) status=(?P<status>\\w+)\\} :: (?P<message>.*)"
    )
    match = re.match(pattern, line.strip())
    if match:
        return match.groupdict()
    return None
''',
}


class OfflineCodeGenAgent:
    """
    离线桩：查表返回预置解析器代码

    接口与 CodeGenAgent 一致，但无需 API Key。用于在没有 LLM 配置时演示完整流程。
    """

    def __init__(self, model: Optional[str] = None):
        """
        初始化离线 Agent

        Args:
            model: 模型名称（仅作展示，不影响预置解析器）
        """
        self.model = model or "offline-canned"

    def generate_parser_code(
        self,
        samples: List[str],
        required_keys: List[str],
        error_report: str,
        feedback: Optional[str] = None,
    ) -> str:
        """
        返回预置的解析器代码

        Args:
            samples: 失败的日志样本列表（本实现不使用）
            required_keys: 必需解析出的字段列表
            error_report: 系统报错信息（本实现不使用）
            feedback: 上一轮测试的反馈（本实现不使用）

        Returns:
            预置的 Python 源码字符串
        """
        key = frozenset(required_keys)
        code = _CANNED_PARSERS.get(key)
        if code is not None:
            return code
        # 未预置该格式：返回一个永远返回 None 的桩
        return (
            "def parse(line: str) -> dict | None:\n"
            "    # 离线模式未预置该格式的解析器\n"
            "    return None\n"
        )
