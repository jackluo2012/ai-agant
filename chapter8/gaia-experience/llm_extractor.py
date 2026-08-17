"""从评估运行中提取候选经验字段的真实 LLM 提取器。"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Iterable, List


def _parse(text: str) -> Dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


class OpenAIExperienceExtractor:
    def __init__(self, model: str | None = None):
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("Install requirements-lite.txt for the real LLM path") from error
        kwargs = {}
        if os.getenv("OPENAI_BASE_URL"):
            kwargs["base_url"] = os.environ["OPENAI_BASE_URL"]
        self.client = OpenAI(**kwargs)
        self.model = model or os.getenv("LLM_MODEL", "gpt-5.6")

    def extract(self, record: Dict[str, Any]) -> Dict[str, Any]:
        evidence = {
            key: value for key, value in record.items()
            if key not in {"applies_when", "observed_strategies", "mistakes", "exceptions"}
        }
        prompt = f"""分析一条经过外部评估的 GAIA 风格代理运行记录。

环境评分是客观依据，不要将失败标记重新标记为成功。
提取候选经验时不要复制完整的轨迹。仅返回 JSON 格式
包含四个简洁字符串数组：
- applies_when：该经验适用的未来条件
- observed_strategies：对该运行有帮助的行动；若无证据支持则为空
- mistakes：与部分成功或失败结果相关的行动或遗漏
- exceptions：不应应用该明显经验的情况

评估的运行记录：
{json.dumps(evidence, ensure_ascii=False, indent=2)}
"""
        response = self.client.responses.create(model=self.model, input=prompt)
        fields = _parse(response.output_text)
        enriched = dict(record)
        for key in ("applies_when", "observed_strategies", "mistakes", "exceptions"):
            value = fields.get(key, [])
            enriched[key] = [str(item) for item in value] if isinstance(value, list) else []
        return enriched

    def extract_all(self, records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        records = list(records)
        evidence = [
            {key: value for key, value in record.items()
             if key not in {"applies_when", "observed_strategies", "mistakes", "exceptions"}}
            for record in records
        ]
        prompt = f"""比较这些经过外部评估的 GAIA 风格代理运行记录。

仅返回 JSON 格式 {{"records": [...]}}。每个输出记录必须包含 id 和
四个字符串数组：applies_when、observed_strategies、mistakes、exceptions。
使用成功/部分成功/失败评分作为证据。最重要的是，将可复用策略
规范化为每个支持它的非失败运行中的完全相同的表述；不要给予失败路径
正面策略的认可。当证据支持以下实验基准锚点之一时，使用其确切文本：
- 使用主要来源验证答案
- 在选择解析器之前检查文件类型
- 根据行数验证计算的总数
这使得后续确定性阶段能够要求至少两个独立运行的支持，并在无需
另一个 LLM 判断器的情况下评分迁移效果。不要复制完整轨迹。

运行记录：
{json.dumps(evidence, ensure_ascii=False, indent=2)}
"""
        response = self.client.responses.create(model=self.model, input=prompt)
        payload = _parse(response.output_text)
        extracted = {item.get("id"): item for item in payload.get("records", [])}
        enriched_records = []
        for record in records:
            enriched = dict(record)
            fields = extracted.get(record["id"], {})
            for key in ("applies_when", "observed_strategies", "mistakes", "exceptions"):
                value = fields.get(key, [])
                enriched[key] = [str(item) for item in value] if isinstance(value, list) else []
            enriched_records.append(enriched)
        return enriched_records
