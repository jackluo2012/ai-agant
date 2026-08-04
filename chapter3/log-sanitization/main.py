#!/usr/bin/env python3
"""
日志脱敏主程序
================

使用统一 LLM 客户端或离线规则引擎检测和脱敏日志中的敏感信息。
自动读取项目根目录 .env 配置，支持大模型和小模型（llama.cpp）。
"""

import os
import sys
import argparse
from collections import Counter
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from config import OUTPUT_DIR
import regex_sanitizer
from samples import SAMPLES


def main(test_id: Optional[str] = None, limit: Optional[int] = None,
         use_small_model: bool = False):
    """
    主函数：运行日志脱敏

    Args:
        test_id: 要处理的特定测试用例 ID（可选）
        limit: 最多处理的测试用例数量（可选）
        use_small_model: 是否使用本地小模型（Ollama）
    """
    print("🚀 启动日志脱敏（LLM 模式）")
    print("=" * 60)

    # 初始化组件
    try:
        from agent import LogSanitizationAgent
        from test_loader import TestCaseLoader

        print("📦 从 user-memory-evaluation 加载测试用例...")
        loader = TestCaseLoader()

        print(f"🤖 初始化 LLM 客户端...")
        agent = LogSanitizationAgent(use_small_model=use_small_model)

    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        print(f"   请检查项目根目录 .env 配置")
        return 1

    # 获取要处理的测试用例
    if test_id:
        print(f"\n📋 处理指定测试用例: {test_id}")
        conversations = loader.get_test_case_conversations(test_id)

        if not conversations:
            print(f"❌ 未找到测试用例 {test_id} 或该用例没有对话")
            return 1

        agent.process_test_case(test_id, conversations)

    else:
        print("\n📋 获取 Layer 3 测试用例...")
        test_cases = loader.get_layer3_test_cases()

        if not test_cases:
            print("❌ 未找到 Layer 3 测试用例")
            return 1

        print(f"找到 {len(test_cases)} 个 Layer 3 测试用例")

        if limit:
            test_cases = test_cases[:limit]
            print(f"处理前 {limit} 个测试用例")

        for i, tc in enumerate(test_cases, 1):
            print(f"\n[{i}/{len(test_cases)}] 测试用例: {tc['test_id']}")
            print(f"   标题: {tc['title']}")
            print(f"   对话数: {tc['num_conversations']}")

            conversations = loader.get_test_case_conversations(tc['test_id'])

            if conversations:
                agent.process_test_case(tc['test_id'], conversations)
            else:
                print(f"   ⚠️  未找到 {tc['test_id']} 的对话")

    print("\n" + "=" * 60)
    print("✅ 日志脱敏完成！")
    print(f"📁 结果已保存到: {OUTPUT_DIR}")

    return 0


def demo_regex_mode():
    """离线规则脱敏演示"""
    print("🎯 离线规则脱敏演示（regex 模式，无需 LLM）")
    print("=" * 60)
    print(f"共 {len(SAMPLES)} 个代表性样本，覆盖密钥/令牌/私钥/PII 等类别\n")

    total = Counter()
    total_hits = 0
    for name, text in SAMPLES:
        redacted, findings = regex_sanitizer.sanitize(text)
        regex_sanitizer.print_report(name, text, redacted, findings)
        total.update(regex_sanitizer.summarize(findings))
        total_hits += len(findings)

    print(f"\n{'=' * 64}")
    print("脱敏类别汇总（所有样本）")
    print("=" * 64)
    for category, count in total.most_common():
        label = regex_sanitizer.CATEGORY_LABELS.get(category, category)
        print(f"   {label:<16} {count} 处")
    print(f"\n   合计脱敏 {total_hits} 处敏感信息，覆盖 {len(total)} 个类别")
    return 0


def sanitize_file(input_path: str, output_path: Optional[str] = None,
                  mode: str = "regex", use_small_model: bool = False):
    """对任意日志文件执行脱敏"""
    in_file = Path(input_path)
    if not in_file.exists():
        print(f"❌ 输入文件不存在: {input_path}")
        return 1

    text = in_file.read_text(encoding="utf-8", errors="replace")
    out_file = Path(output_path) if output_path else in_file.with_suffix(in_file.suffix + ".sanitized")

    if mode == "regex":
        print(f"🔍 使用离线规则引擎脱敏: {input_path}")
        redacted, findings = regex_sanitizer.sanitize(text)
        counts = regex_sanitizer.summarize(findings)
    else:
        print(f"🔍 使用 LLM 脱敏: {input_path}")
        try:
            from agent import LogSanitizationAgent
        except Exception as e:
            print(f"❌ 加载 LLM 引擎失败: {e}")
            return 1
        agent = LogSanitizationAgent(use_small_model=use_small_model)
        pii_values, _ = agent.detect_pii(text)
        redacted, _ = agent.sanitize_text(text, pii_values)
        counts = Counter({"pii": len(pii_values)})
        findings = pii_values

    out_file.write_text(redacted, encoding="utf-8")

    print(f"\n✅ 已写入脱敏结果: {out_file}")
    print(f"   共脱敏 {sum(counts.values())} 处敏感信息")
    for category, count in counts.most_common():
        label = regex_sanitizer.CATEGORY_LABELS.get(category, category)
        print(f"   - {label}: {count} 处")
    return 0


def demo_mode(use_small_model: bool = False):
    """运行演示模式（LLM 模式）"""
    print("🎯 运行演示模式（LLM）")
    print("=" * 60)

    sample_conversation = {
        'conversation_id': 'demo_001',
        'timestamp': '2024-01-01 10:00:00',
        'messages': [
            {
                'role': 'user',
                'content': '我需要更新我的信息。我的社保号是 123-45-6789。'
            },
            {
                'role': 'assistant',
                'content': '我可以帮您更新信息。请确认您的信用卡号？'
            },
            {
                'role': 'user',
                'content': '好的，是 4532 1234 5678 9012。另外，我的病历号是 MRN-789456。'
            },
            {
                'role': 'assistant',
                'content': '谢谢。我已经记录了您的社保号（尾号 6789）和信用卡（尾号 9012）。'
            },
            {
                'role': 'user',
                'content': '好的。我的驾照号是 DL-123456789，护照号是 P987654321。'
            }
        ]
    }

    try:
        from agent import LogSanitizationAgent
        agent = LogSanitizationAgent(use_small_model=use_small_model)
        print("\n📝 已创建包含 Level 3 PII 的示例对话")
        print("🔍 正在检测和脱敏 PII...\n")

        result = agent.sanitize_conversation(sample_conversation, 'demo')

        print("\n" + "=" * 60)
        print("演示结果")
        print("=" * 60)
        print(f"发现 PII 项: {len(result['pii_found'])}")
        for pii in result['pii_found']:
            print(f"  - {pii}")

        print(f"\n替换次数: {result['replacements_made']}")
        print("\n--- 脱敏后的文本 ---")
        print(result['sanitized_text'])

        agent.save_sanitized_log('demo', [result])
        agent.metrics_collector.save_metrics()
        agent.metrics_collector.print_summary()

    except Exception as e:
        print(f"❌ 演示失败: {e}")
        return 1

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="日志脱敏实验：从 Agent 日志/工具输出中检测并脱敏敏感信息"
                    "（API 密钥、令牌、私钥、信用卡、身份证、手机号、邮箱等）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
两种脱敏引擎：
  regex  离线规则引擎（默认），基于正则+校验算法，无需 LLM，结果确定、速度快
  llm    LLM 引擎，使用项目根目录 .env 配置的模型

常用示例：
  python main.py --demo                       # 离线跑内置样本
  python main.py --demo --mode llm            # 用 LLM 跑演示（使用 .env 配置）
  python main.py --input app.log              # 离线脱敏日志文件
  python main.py --input app.log -o out.log   # 指定输出文件
  python main.py --input app.log --mode llm   # 用 LLM 脱敏文件
  python main.py                              # 批量处理评测框架中的 Layer 3 用例
  python main.py --test-id layer3_01_travel_coordination
  python main.py --limit 3

小模型模式（llama.cpp）：
  python main.py --demo --mode llm --small-model   # 使用 llama.cpp 小模型
  python main.py --input app.log --mode llm --small-model

配置说明：
  LLM 模式会自动读取项目根目录的 .env 配置文件。
  大模型配置（当前）：LLM_PROVIDER=aliyun, LLM_MODEL=qwen3.7-max-2026-05-20
  小模型配置（llama.cpp）：192.168.1.158:11434，模型 MiniCPM5-1B-Q4_K_M.gguf
""",
    )

    parser.add_argument(
        '--mode',
        choices=['regex', 'llm'],
        default='regex',
        help='脱敏引擎：regex=离线规则（默认），llm=LLM 模型'
    )

    parser.add_argument(
        '-i', '--input',
        type=str,
        metavar='FILE',
        help='待脱敏的日志文件路径'
    )

    parser.add_argument(
        '-o', '--output',
        type=str,
        metavar='FILE',
        help='脱敏结果输出文件路径'
    )

    parser.add_argument(
        '--small-model',
        action='store_true',
        help='使用本地小模型（llama.cpp）'
    )

    parser.add_argument(
        '--test-id',
        type=str,
        help='仅处理指定 ID 的评测用例'
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='最多处理多少个评测用例'
    )

    parser.add_argument(
        '--demo',
        action='store_true',
        help='运行演示'
    )

    args = parser.parse_args()

    if args.input:
        exit_code = sanitize_file(
            args.input, args.output,
            mode=args.mode,
            use_small_model=args.small_model
        )
    elif args.demo:
        if args.mode == 'llm':
            exit_code = demo_mode(use_small_model=args.small_model)
        else:
            exit_code = demo_regex_mode()
    else:
        exit_code = main(
            test_id=args.test_id,
            limit=args.limit,
            use_small_model=args.small_model
        )

    sys.exit(exit_code)
