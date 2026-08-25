"""实验 8-7 纵向评估测试"""

import sys
import os

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

import json
import unittest
from pathlib import Path

from agent import ReferenceAgent
from harness import LongitudinalEvaluator


# 加载测试任务数据
TASKS = json.loads(Path(__file__).with_name("dataset.json").read_text(encoding="utf-8"))["tasks"]


class LongitudinalEvaluationTest(unittest.TestCase):
    """纵向评估测试类"""

    def test_evolving_agent_transfers_updates_and_retains(self):
        """
        测试演化代理能够迁移更新并保留知识

        验证：
        - 迁移准确率为 100%
        - 变更信号后 1 个任务恢复
        - 保留率为 100%
        - 存储空间大于 0
        """
        report = LongitudinalEvaluator().run(ReferenceAgent("evolving"), TASKS)
        self.assertEqual(1.0, report["transfer_accuracy"])
        self.assertEqual(1, report["adaptation"]["tasks_after_change_signal_to_recover"])
        self.assertEqual(1.0, report["retention_rate"])
        self.assertGreater(report["cost"]["storage_bytes"], 0)

    def test_append_only_agent_cannot_replace_changed_rule(self):
        """
        测试仅追加代理无法替换已更改的规则

        验证：
        - 变更阶段准确率为 0%
        - 保留率小于 100%
        - 存在负迁移
        """
        report = LongitudinalEvaluator().run(ReferenceAgent("append_only"), TASKS)
        self.assertEqual(0.0, report["phase_accuracy"]["change"])
        self.assertLess(report["retention_rate"], 1.0)
        self.assertGreater(report["negative_transfer_rate"], 0.0)

    def test_static_agent_does_not_look_like_continual_learning(self):
        """
        测试静态代理不表现出持续学习特征

        验证：
        - 迁移准确率为 0%
        - 存储空间为 0
        """
        report = LongitudinalEvaluator().run(ReferenceAgent("static"), TASKS)
        self.assertEqual(0.0, report["transfer_accuracy"])
        self.assertEqual(0, report["cost"]["storage_bytes"])

    def test_all_four_phases_are_reported(self):
        """
        测试所有四个阶段都被报告

        验证：
        - 四个阶段都在报告中
        - 学习曲线包含 6 个点
        """
        report = LongitudinalEvaluator().run(ReferenceAgent("evolving"), TASKS)
        self.assertEqual({"learning", "transfer", "change", "retention"}, set(report["phase_accuracy"]))
        self.assertEqual(6, len(report["learning_curve"]))

    def test_replacement_and_update_activation_are_separate_metrics(self):
        """
        测试替换和更新激活是独立的指标

        验证演化代理和仅追加代理在替换和更新指标上的差异
        """
        evolving = LongitudinalEvaluator().run(ReferenceAgent("evolving"), TASKS)
        append_only = LongitudinalEvaluator().run(ReferenceAgent("append_only"), TASKS)
        self.assertEqual(1.0, evolving["replacement"]["rule_replacement_accuracy"])
        self.assertEqual(0.0, evolving["replacement"]["obsolete_rule_reference_rate"])
        self.assertEqual(0.0, append_only["replacement"]["rule_replacement_accuracy"])
        self.assertEqual(1.0, append_only["replacement"]["obsolete_rule_reference_rate"])
        self.assertEqual(1.0, evolving["update_metrics"]["artifact_activation_rate"])
        self.assertEqual(1.0, evolving["update_metrics"]["memory_adherence_rate"])


if __name__ == "__main__":
    unittest.main()
