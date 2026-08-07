"""
LLM 辅助模块 - 用于安全检查、审批和摘要

本模块使用项目统一的 LLM 客户端，提供：
- 危险操作的安全审批
- 复杂输出的智能摘要
- 错误分析和建议
- 代码语法验证
"""

import json
import sys
import os
from typing import Optional, Dict, Any

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

from config import Config


def _reasoning_safe_temperature(model, requested=1.0):
    """
    推理模型（如 Kimi K3、GPT-5）只接受 temperature=1

    对于这些模型返回 1，其他模型返回请求的值

    Args:
        model: 模型名称
        requested: 请求的温度值

    Returns:
        适用的温度值
    """
    m = str(model or "").lower().replace("/", "-")
    return 1 if ("kimi-k3" in m or "gpt-5" in m) else requested


def _parse_json_response(content):
    """
    从 LLM 回复中解析 JSON 对象，容忍 markdown 代码块

    推理模型（特别是 kimi-k3）会返回有效的 JSON，但会包裹在
    ```json ... ``` 代码块中，导致直接 json.loads() 失败。

    Args:
        content: LLM 返回的内容

    Returns:
        解析后的 JSON 对象

    Raises:
        json.JSONDecodeError: 如果无法解析为有效 JSON
    """
    text = (content or "").strip()
    if text.startswith("```"):
        # 去除开头和结尾的代码块标记
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 最后的尝试：从第一个 { 到最后一个 } 提取
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


class LLMHelper:
    """LLM 辅助类，用于基于大模型的各种操作"""

    def __init__(self):
        """
        初始化 LLM 辅助类

        LLM 客户端采用延迟初始化，使不需要 LLM 的执行工具
        （如 Python 代码执行、终端命令、文件写入）可以在没有
        API 密钥的情况下离线工作。
        """
        self.client = None
        self.model = None

    def _ensure_client(self) -> None:
        """
        确保客户端已初始化（首次使用时创建）

        Raises:
            ValueError: 如果无法获取 LLM 客户端
        """
        if self.client is None:
            if get_llm_client is None:
                raise ValueError("LLM 客户端模块不可用")
            self.client = get_llm_client()
            self.model = self.client.model_name

    def request_approval(
        self,
        operation: str,
        details: Dict[str, Any]
    ) -> tuple[bool, str]:
        """
        请求 LLM 审批危险操作

        Args:
            operation: 操作名称
            details: 操作详情

        Returns:
            (是否批准, 原因说明) 元组
        """
        prompt = f"""你是一个 AI 代理执行系统的安全审查员。
请审查以下操作并决定是否应该批准。

操作：{operation}
详情：{json.dumps(details, indent=2, ensure_ascii=False)}

请从以下方面分析该操作：
1. 潜在的数据丢失或破坏性操作
2. 安全风险
3. 资源消耗问题
4. 是否符合最佳实践

请以 JSON 格式回复：
{{
    "approved": true/false,
    "reason": "决策的简要说明",
    "risk_level": "low/medium/high",
    "recommendations": ["如有建议请列出"]
}}
"""

        try:
            self._ensure_client()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个谨慎的安全审查员。批准安全的操作，拒绝有风险的操作。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=_reasoning_safe_temperature(self.model, 0.1),
                max_tokens=Config.MAX_TOKENS
            )

            result = _parse_json_response(response.choices[0].message.content)
            return result["approved"], result["reason"]

        except Exception as e:
            # 如果审批检查失败，默认拒绝以确保安全
            return False, f"审批检查失败：{str(e)}"

    def summarize_output(
        self,
        tool_name: str,
        output: str
    ) -> str:
        """
        摘要复杂的工具输出

        Args:
            tool_name: 产生输出的工具名称
            output: 待摘要的输出内容

        Returns:
            摘要后的输出
        """
        prompt = f"""请摘要来自 '{tool_name}' 工具的以下输出。
重点关注：
1. 关键结果或发现
2. 错误或警告
3. 重要的模式或洞察
4. 可操作的信息

待摘要的输出：
{output[:5000]}  # 限制输入长度以避免超出 token 限制

请提供简洁的摘要，捕捉关键信息。"""

        try:
            self._ensure_client()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是技术输出摘要专家。请简洁明了，专注于可操作的信息。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=_reasoning_safe_temperature(self.model, 0.1),
                max_tokens=Config.MAX_TOKENS
            )

            summary = response.choices[0].message.content
            return f"[摘要输出]\n{summary}\n\n[原始输出长度：{len(output)} 字符]"

        except Exception as e:
            return f"[摘要失败：{str(e)}]\n\n{output[:Config.MAX_OUTPUT_LENGTH]}..."

    def analyze_error(
        self,
        tool_name: str,
        command: str,
        error_output: str
    ) -> str:
        """
        分析错误输出并提供建议

        Args:
            tool_name: 产生错误的工具名称
            command: 失败的命令或代码
            error_output: 错误输出

        Returns:
            包含建议的分析结果
        """
        prompt = f"""请分析来自 '{tool_name}' 工具的以下错误：

命令/代码：
{command}

错误输出：
{error_output[:3000]}

请提供：
1. 根本原因分析
2. 建议的修复方法
3. 预防策略

请简洁实用。"""

        try:
            self._ensure_client()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是调试专家。分析错误并提供清晰、可操作的解决方案。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=_reasoning_safe_temperature(self.model, 0.2),
                max_tokens=Config.MAX_TOKENS
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"错误分析失败：{str(e)}"

    def verify_code_syntax(
        self,
        code: str,
        language: str = "python"
    ) -> tuple[bool, Optional[str]]:
        """
        验证代码语法并提供反馈

        Args:
            code: 待验证的代码
            language: 编程语言

        Returns:
            (是否有效, 错误消息) 元组
        """
        # 对于 Python，可以进行实际的语法检查
        if language == "python":
            try:
                compile(code, "<string>", "exec")
                return True, None
            except SyntaxError as e:
                return False, f"语法错误（第 {e.lineno} 行）：{e.msg}"

        # 对于其他语言，使用 LLM 进行基本验证
        prompt = f"""请检查以下 {language} 代码的语法错误：

```{language}
{code}
```

请以 JSON 格式回复：
{{
    "valid": true/false,
    "errors": ["如有语法错误请列出"],
    "warnings": ["如有警告请列出"]
}}
"""

        try:
            self._ensure_client()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": f"你是 {language} 语法验证器。请检查代码的语法错误。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=_reasoning_safe_temperature(self.model, 0.1),
                max_tokens=Config.MAX_TOKENS
            )

            result = _parse_json_response(response.choices[0].message.content)
            if result["valid"]:
                return True, None
            else:
                return False, "; ".join(result.get("errors", []))

        except Exception as e:
            # 如果验证失败，允许代码通过
            return True, None
