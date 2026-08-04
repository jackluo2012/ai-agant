"""
日志脱敏 Agent
================

使用统一 LLM 客户端检测和脱敏敏感信息（PII）。
自动读取项目根目录 .env 配置，支持大模型（阿里云等）和小模型（llama.cpp）。
"""

import os
import sys
import time
import re
import json
from typing import List, Tuple, Dict, Optional
from pathlib import Path

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from llm.client import get_llm_client, get_llm_config
except ImportError:
    get_llm_client = None
    get_llm_config = None

from config import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    PII_DETECTION_SCHEMA,
    OUTPUT_DIR
)
from metrics import PerformanceMetrics, MetricsCollector


class LogSanitizationAgent:
    """使用统一 LLM 客户端进行日志脱敏的 Agent

    支持两种运行模式：
    1. 默认模式：自动读取 .env 配置（阿里云大模型等）
    2. 小模型模式：使用 llama.cpp 本地小模型
    """

    def __init__(self, use_small_model: bool = False):
        """
        初始化脱敏 Agent

        Args:
            use_small_model: 是否使用小模型（llama.cpp）
                           False=使用 .env 配置的模型（默认）
                           True=使用 llama.cpp 本地小模型
        """
        if get_llm_client is None:
            raise ImportError("无法导入 llm.client，请确保在项目根目录运行")

        self.metrics_collector = MetricsCollector(OUTPUT_DIR)

        # 初始化 LLM 客户端
        try:
            if use_small_model:
                # 使用 llama.cpp 小模型
                print("🔄 使用 llama.cpp 小模型...")
                self.client = get_llm_client(
                    provider="custom",
                    model="MiniCPM5-1B-Q4_K_M.gguf",
                    base_url="http://192.168.1.158:11434/v1"
                )
                self.model = self.client.model_name
                print(f"✅ 已连接 llama.cpp: 192.168.1.158:11434/{self.model}")
            else:
                # 使用 .env 配置的模型
                self.client = get_llm_client()
                self.model = self.client.model_name
                print(f"✅ LLM 客户端已初始化: {self.client.provider}/{self.model}")

        except Exception as e:
            print(f"❌ 初始化 LLM 客户端失败: {e}")
            print(f"   请检查项目根目录 .env 配置")
            raise

    def _chat_stream(self, messages):
        """从 LLM 获取流式响应"""
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=0.1,
            max_tokens=1000,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            yield chunk.choices[0].delta.content or ""

    def count_tokens(self, text: str) -> int:
        """估算 token 数量（粗略近似）"""
        return len(text) // 4

    def detect_pii(self, conversation_text: str) -> Tuple[List[str], Dict]:
        """
        使用 LLM 检测对话文本中的 Level 3 PII

        Args:
            conversation_text: 待分析的文本

        Returns:
            - 检测到的 PII 值列表
            - 性能指标字典
        """
        # 准备提示词
        user_prompt = USER_PROMPT_TEMPLATE.format(conversation_text=conversation_text)

        # 统计输入 tokens
        input_tokens = self.count_tokens(SYSTEM_PROMPT + user_prompt)

        # 测量首字时间（TTFT）
        start_time = time.perf_counter()

        # 创建消息
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        # 跟踪首字时间
        first_token_time = None
        output_tokens_count = 0
        full_response = ""

        try:
            print("   🧠 分析中: \033[90m", end="", flush=True)

            for content in self._chat_stream(messages):
                if first_token_time is None and content:
                    first_token_time = time.perf_counter()

                full_response += content
                output_tokens_count += len(content) // 4

                if content:
                    print(content, end="", flush=True)

            print("\033[0m")

        except Exception as e:
            print(f"\n❌ PII 检测出错: {e}")
            return [], {}

        end_time = time.perf_counter()

        # 计算性能指标
        prefill_time_ms = (first_token_time - start_time) * 1000 if first_token_time else 0
        total_time_ms = (end_time - start_time) * 1000
        output_time_ms = total_time_ms - prefill_time_ms

        prefill_speed = input_tokens / (prefill_time_ms / 1000) if prefill_time_ms > 0 else 0
        output_speed = output_tokens_count / (output_time_ms / 1000) if output_time_ms > 0 else 0

        # 解析 JSON 响应
        pii_values = []

        try:
            if "```json" in full_response:
                json_start = full_response.find("```json") + 7
                json_end = full_response.find("```", json_start)
                json_str = full_response[json_start:json_end].strip()
            elif "[" in full_response:
                json_start = full_response.find("[")
                json_end = full_response.rfind("]") + 1
                json_str = full_response[json_start:json_end]
            else:
                json_str = full_response

            response_json = json.loads(json_str)

            if isinstance(response_json, dict):
                pii_values = response_json.get('pii_values') or []
            elif isinstance(response_json, list):
                pii_values = response_json

            cleaned_pii_values = []
            for pii in pii_values:
                if pii and isinstance(pii, str):
                    cleaned = pii.strip().strip('-').strip()
                    if cleaned:
                        cleaned_pii_values.append(cleaned)
            pii_values = cleaned_pii_values

        except (json.JSONDecodeError, ValueError) as e:
            print(f"\n   ⚠️  JSON 解析失败: {e}")
            pii_values = [line.strip().strip('"\'')
                         for line in full_response.split('\n')
                         if line.strip() and line.strip() not in ['[', ']', ',']]

        metrics = {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens_count,
            'prefill_time_ms': prefill_time_ms,
            'output_time_ms': output_time_ms,
            'total_time_ms': total_time_ms,
            'prefill_speed_tps': prefill_speed,
            'output_speed_tps': output_speed,
            'pii_items_found': len(pii_values)
        }

        return pii_values, metrics

    def sanitize_text(self, text: str, pii_values: List[str]) -> Tuple[str, int]:
        """将文本中的 PII 值替换为 [REDACTED]"""
        sanitized = text
        replacements = 0

        for pii_value in pii_values:
            escaped_value = re.escape(pii_value)
            occurrences = len(re.findall(escaped_value, sanitized, re.IGNORECASE))
            sanitized = re.sub(escaped_value, '[REDACTED]', sanitized, flags=re.IGNORECASE)
            replacements += occurrences

        return sanitized, replacements

    def sanitize_conversation(
        self,
        conversation: Dict,
        test_id: str = "unknown"
    ) -> Dict:
        """对单个对话进行脱敏并收集指标"""
        conv_text = self.format_conversation(conversation)
        conv_id = conversation.get('conversation_id', 'unknown')

        print(f"🔍 处理对话: {conv_id}")

        pii_values, perf_metrics = self.detect_pii(conv_text)

        if pii_values:
            print(f"   ✅ 发现 {len(pii_values)} 个 PII 项:")
            for pii in pii_values:
                print(f"      - {pii}")
        else:
            print("   ⚠️  未检测到 PII")

        sanitized_text, replacements = self.sanitize_text(conv_text, pii_values)

        metric = PerformanceMetrics(
            test_id=test_id,
            conversation_id=conv_id,
            input_text_length=len(conv_text),
            input_tokens=perf_metrics.get('input_tokens', 0),
            prefill_time_ms=perf_metrics.get('prefill_time_ms', 0),
            output_time_ms=perf_metrics.get('output_time_ms', 0),
            total_time_ms=perf_metrics.get('total_time_ms', 0),
            output_tokens=perf_metrics.get('output_tokens', 0),
            prefill_speed_tps=perf_metrics.get('prefill_speed_tps', 0),
            output_speed_tps=perf_metrics.get('output_speed_tps', 0),
            pii_items_found=perf_metrics.get('pii_items_found', 0),
            replacements_made=replacements,
            sanitized_text_length=len(sanitized_text)
        )

        self.metrics_collector.add_metric(metric)

        return {
            'conversation_id': conv_id,
            'original_length': len(conv_text),
            'sanitized_length': len(sanitized_text),
            'pii_found': pii_values,
            'replacements_made': replacements,
            'sanitized_text': sanitized_text,
            'metrics': metric.to_dict()
        }

    def format_conversation(self, conversation: Dict) -> str:
        """将对话字典格式化为文本"""
        lines = []
        lines.append(f"对话 ID: {conversation.get('conversation_id', 'unknown')}")
        lines.append(f"时间戳: {conversation.get('timestamp', 'unknown')}")
        lines.append("-" * 50)

        messages = conversation.get('messages', [])
        for msg in messages:
            role = msg.get('role', 'unknown').upper()
            content = msg.get('content', '')
            lines.append(f"{role}: {content}")
            lines.append("")

        return "\n".join(lines)

    def save_sanitized_log(self, test_id: str, results: List[Dict]):
        """保存脱敏日志到输出目录"""
        output_file = OUTPUT_DIR / f"{test_id}_sanitized.txt"
        summary_file = OUTPUT_DIR / f"{test_id}_summary.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            for result in results:
                f.write(f"\n{'='*60}\n")
                f.write(f"对话: {result['conversation_id']}\n")
                f.write(f"{'='*60}\n")
                f.write(result['sanitized_text'])
                f.write("\n")

        summary = {
            'test_id': test_id,
            'total_conversations': len(results),
            'total_pii_found': sum(len(r['pii_found']) for r in results),
            'total_replacements': sum(r['replacements_made'] for r in results),
            'conversations': [
                {
                    'conversation_id': r['conversation_id'],
                    'pii_count': len(r['pii_found']),
                    'replacements': r['replacements_made']
                }
                for r in results
            ]
        }

        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        print(f"✅ 脱敏日志已保存: {output_file}")
        print(f"✅ 摘要已保存: {summary_file}")

    def process_test_case(self, test_id: str, conversations: List[Dict]) -> List[Dict]:
        """处理测试用例中的所有对话"""
        results = []

        print(f"\n{'='*60}")
        print(f"处理测试用例: {test_id}")
        print(f"对话总数: {len(conversations)}")
        print(f"{'='*60}")

        for i, conv in enumerate(conversations, 1):
            print(f"\n[{i}/{len(conversations)}] ", end="")
            result = self.sanitize_conversation(conv, test_id)
            results.append(result)

        self.save_sanitized_log(test_id, results)
        self.metrics_collector.save_metrics()
        self.metrics_collector.print_summary()

        return results
