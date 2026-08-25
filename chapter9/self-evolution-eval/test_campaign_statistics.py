"""实验 8-7 活动统计测试"""

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

import unittest

from run_experiment_8_7 import describe


class CampaignStatisticsTest(unittest.TestCase):
    """活动统计测试类"""

    def test_repeated_run_statistics_report_t_interval(self):
        """
        测试重复运行的统计报告 T 区间

        验证 describe 函数能正确计算样本数、均值、标准差和置信区间
        """
        result = describe([0.0, 0.5, 1.0])
        self.assertEqual(3, result["n"])
        self.assertEqual(0.5, result["mean"])
        self.assertGreater(result["sample_stdev"], 0)
        self.assertLess(result["ci95_t"][0], result["mean"])
        self.assertGreater(result["ci95_t"][1], result["mean"])


if __name__ == "__main__":
    unittest.main()
