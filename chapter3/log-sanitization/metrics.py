"""
性能指标模块
============
"""

import time
import json
from typing import Dict, List
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class PerformanceMetrics:
    """存储单次脱敏操作的性能指标"""
    test_id: str
    conversation_id: str
    input_text_length: int
    input_tokens: int

    # 时间指标
    prefill_time_ms: float  # 首字时间（TTFT）
    output_time_ms: float
    total_time_ms: float

    # Token 指标
    output_tokens: int
    prefill_speed_tps: float  # tokens per second
    output_speed_tps: float

    # 脱敏结果
    pii_items_found: int
    replacements_made: int
    sanitized_text_length: int

    # 时间戳
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        """转换为字典用于 JSON 序列化"""
        return asdict(self)


class MetricsCollector:
    """收集和汇总性能指标"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.metrics_file = output_dir / "performance_metrics.json"
        self.summary_file = output_dir / "performance_summary.json"
        self.metrics: List[PerformanceMetrics] = []

    def add_metric(self, metric: PerformanceMetrics):
        """添加新指标到集合"""
        self.metrics.append(metric)

    def calculate_summary(self) -> Dict:
        """计算所有指标的汇总统计"""
        if not self.metrics:
            return {"error": "未收集到指标"}

        # 收集每个指标的所有值
        prefill_times = [m.prefill_time_ms for m in self.metrics]
        output_times = [m.output_time_ms for m in self.metrics]
        total_times = [m.total_time_ms for m in self.metrics]

        input_tokens = [m.input_tokens for m in self.metrics]
        output_tokens = [m.output_tokens for m in self.metrics]

        prefill_speeds = [m.prefill_speed_tps for m in self.metrics]
        output_speeds = [m.output_speed_tps for m in self.metrics]

        pii_counts = [m.pii_items_found for m in self.metrics]
        replacements = [m.replacements_made for m in self.metrics]

        def calculate_stats(values: List[float]) -> Dict:
            """计算列表的最小值、最大值、平均值、中位数"""
            if not values:
                return {"min": 0, "max": 0, "mean": 0, "median": 0}

            sorted_values = sorted(values)
            n = len(sorted_values)

            return {
                "min": min(values),
                "max": max(values),
                "mean": sum(values) / n,
                "median": sorted_values[n // 2] if n % 2 == 1 else (
                    sorted_values[n // 2 - 1] + sorted_values[n // 2]
                ) / 2
            }

        summary = {
            "total_conversations": len(self.metrics),
            "timestamp": datetime.now().isoformat(),

            "timing_metrics": {
                "prefill_time_ms": calculate_stats(prefill_times),
                "output_time_ms": calculate_stats(output_times),
                "total_time_ms": calculate_stats(total_times)
            },

            "token_metrics": {
                "input_tokens": calculate_stats(input_tokens),
                "output_tokens": calculate_stats(output_tokens),
                "total_input_tokens": sum(input_tokens),
                "total_output_tokens": sum(output_tokens)
            },

            "speed_metrics": {
                "prefill_speed_tps": calculate_stats(prefill_speeds),
                "output_speed_tps": calculate_stats(output_speeds)
            },

            "sanitization_metrics": {
                "pii_items_found": calculate_stats(pii_counts),
                "replacements_made": calculate_stats(replacements),
                "total_pii_found": sum(pii_counts),
                "total_replacements": sum(replacements)
            }
        }

        return summary

    def save_metrics(self):
        """保存所有指标和汇总到文件"""
        # 保存详细指标
        metrics_data = [m.to_dict() for m in self.metrics]
        with open(self.metrics_file, 'w', encoding='utf-8') as f:
            json.dump(metrics_data, f, indent=2, ensure_ascii=False)

        # 保存汇总
        summary = self.calculate_summary()
        with open(self.summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        print(f"✅ 指标已保存: {self.metrics_file}")
        print(f"✅ 汇总已保存: {self.summary_file}")

    def print_summary(self):
        """打印人类可读的指标汇总"""
        summary = self.calculate_summary()

        print("\n" + "=" * 60)
        print("性能指标汇总")
        print("=" * 60)

        print(f"\n📊 总对话数: {summary['total_conversations']}")

        print("\n⏱️  时间指标（毫秒）:")
        timing = summary['timing_metrics']
        print(f"   首字时间（TTFT）: {timing['prefill_time_ms']['mean']:.2f} ms "
              f"(中位数: {timing['prefill_time_ms']['median']:.2f})")
        print(f"   输出时间:    {timing['output_time_ms']['mean']:.2f} ms "
              f"(中位数: {timing['output_time_ms']['median']:.2f})")
        print(f"   总时间:     {timing['total_time_ms']['mean']:.2f} ms "
              f"(中位数: {timing['total_time_ms']['median']:.2f})")

        print("\n📝 Token 指标:")
        tokens = summary['token_metrics']
        print(f"   平均输入 Tokens:  {tokens['input_tokens']['mean']:.1f}")
        print(f"   平均输出 Tokens: {tokens['output_tokens']['mean']:.1f}")
        print(f"   总处理 Tokens: {tokens['total_input_tokens'] + tokens['total_output_tokens']}")

        print("\n⚡ 速度指标（tokens/秒）:")
        speed = summary['speed_metrics']
        print(f"   首字速度: {speed['prefill_speed_tps']['mean']:.1f} tok/s")
        print(f"   输出速度:  {speed['output_speed_tps']['mean']:.1f} tok/s")

        print("\n🔒 脱敏结果:")
        sanitization = summary['sanitization_metrics']
        print(f"   总发现 PII 项:     {sanitization['total_pii_found']}")
        print(f"   总替换次数:   {sanitization['total_replacements']}")
        print(f"   平均每对话 PII 数: {sanitization['pii_items_found']['mean']:.1f}")

        print("\n" + "=" * 60)
