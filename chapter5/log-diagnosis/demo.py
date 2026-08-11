"""
demo.py —— 实验 5-8：生产日志的智能诊断系统（全流程演示）

流水线：
  读轨迹集合 + 架构 + PRD
    -> [LLM] 诊断：定位问题、结构化报告(优先级/模块/描述/建议)
    -> [LLM] 生成回归测试用例(引用轨迹ID+交互轮次)
    -> 重放框架真正执行：先复现 bug(FAIL)，再验证修复(PASS)
    -> (mock) 通过 MCP 对接 GitHub 创建 Issue

运行：
  python demo.py                 # 完整流程（两次真实 LLM 调用，GitHub 步骤默认 mock）
  python demo.py --smoke         # 快速自检：跳过 LLM，用内置用例仅跑重放+GitHub mock
  python demo.py --model <模型>  # 临时切换模型
  python demo.py --create-issue  # 真正经 MCP 创建 GitHub Issue（需 GITHUB_TOKEN+GITHUB_REPO）
  python demo.py -h              # 查看全部参数

配置：
  LLM 配置在项目根目录 .env 文件中设置
  GitHub 相关配置通过环境变量设置
"""

import argparse
import json
import os
import sys

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from diagnoser import Diagnoser
import replay
import github_mcp

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DEFAULT_OUTPUT = os.path.join(HERE, "output", "github_issues.json")

# --smoke 自检用的内置样例：与 LLM 在本数据集上的稳定产物一致，
# 使得无需联网/无需 API Key 即可验证 重放框架 + GitHub mock 的端到端管道。
_CANNED_PROBLEMS = [
    {"title": "未进行退款资格校验", "priority": "P0", "module": "order_service",
     "description": "退款前缺失强制的 verify_refund_eligibility 校验。", "prd_ref": "R1",
     "trajectory_ids": ["T-1001", "T-1002"], "focus_turns": [3]},
    {"title": "支付重试机制未正确实现", "priority": "P0", "module": "payment_service",
     "description": "process_refund 反复失败、无退避、且最终误报成功。", "prd_ref": "R2",
     "trajectory_ids": ["T-1002"], "focus_turns": [7]},
    {"title": "库存查询延迟未降级处理", "priority": "P1", "module": "inventory_service",
     "description": "check_stock 延迟 8300ms 超时未降级。", "prd_ref": "R3",
     "trajectory_ids": ["T-1003"], "focus_turns": [3]},
]
_CANNED_TEST_CASES = [
    {"test_id": "RT-001", "trajectory_id": "T-1001", "focus_turn": 3,
     "description": "退款前必须先做资格校验",
     "assertion": {"type": "step_present", "params": {"tool": "verify_refund_eligibility"}}},
    {"test_id": "RT-002", "trajectory_id": "T-1002", "focus_turn": 7,
     "description": "process_refund 应最终成功且无『多次失败后误报成功』",
     "assertion": {"type": "tool_succeeds", "params": {"tool": "process_refund"}}},
    {"test_id": "RT-003", "trajectory_id": "T-1003", "focus_turn": 3,
     "description": "check_stock 延迟应低于 5000ms",
     "assertion": {"type": "latency_under", "params": {"tool": "check_stock", "threshold_ms": 5000}}},
]


def _read(data_dir, name):
    """读取数据文件"""
    with open(os.path.join(data_dir, name), "r", encoding="utf-8") as f:
        return f.read()


def _traj_path(data_dir):
    """获取轨迹文件路径"""
    return os.path.join(data_dir, "trajectories.jsonl")


def _hr(title):
    """打印标题分隔符"""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def _replay_and_issues(problems, test_cases, do_github=True,
                       traj_path=None, out_path=DEFAULT_OUTPUT, create_issue=False):
    """
    步骤 3/4：对同一输入重放被测系统并断言，再生成 GitHub Issue（默认 mock）

    对 fixed=False / fixed=True 各重放一次，演示同一条回归用例的
    『失败(复现bug)』与『通过(验证修复)』。返回 (复现数, 验证数)。
    """
    traj_path = traj_path or replay._DATA
    _hr("步骤 3｜重放框架真正执行测试用例")
    print("(A) 对『线上未修复』系统重放 —— 期望复现 bug（FAIL）")
    buggy = replay.run_suite(test_cases, fixed=False, path=traj_path)
    for r in buggy:
        flag = "PASS" if r["passed"] else "FAIL"
        print(f"    [{flag}] {r['test_id']}  ({r.get('trajectory_id')})  {r['detail']}")

    print("\n(B) 对『修复后』系统重放 —— 期望修复被验证（PASS）")
    fixed = replay.run_suite(test_cases, fixed=True, path=traj_path)
    for r in fixed:
        flag = "PASS" if r["passed"] else "FAIL"
        print(f"    [{flag}] {r['test_id']}  ({r.get('trajectory_id')})  {r['detail']}")

    reproduced = sum(1 for r in buggy if not r["passed"])
    verified = sum(1 for r in fixed if r["passed"])
    print(f"\n  小结：复现 bug {reproduced}/{len(buggy)} 条；修复后通过 {verified}/{len(fixed)} 条。")

    if do_github:
        token, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPO")
        if create_issue and token and repo:
            _hr(f"步骤 4｜通过 MCP 对接 GitHub 在 {repo} 真实创建 Issue")
            github_mcp.create_issues(problems, test_cases, mock=False,
                                     out_path=out_path, repo=repo, token=token)
        else:
            if create_issue:
                print("\n[提示] --create-issue 需要 GITHUB_TOKEN 与 GITHUB_REPO(owner/repo)，"
                      "当前缺失，已回退到 mock。")
            _hr("步骤 4｜通过 MCP 对接 GitHub 创建 Issue（mock，不联网）")
            github_mcp.create_issues(problems, test_cases, mock=True, out_path=out_path)
    return reproduced, verified


def run_smoke(data_dir=DATA, out_path=DEFAULT_OUTPUT):
    """
    快速自检：不调用 LLM，用内置样例仅跑 重放框架 + GitHub mock 的端到端管道

    退出码：管道全绿(复现全部 + 验证全部)返回 0，否则返回 3。
    """
    _hr("自检模式（--smoke）：跳过 LLM，用内置诊断结果验证重放+GitHub mock 管道")
    reproduced, verified = _replay_and_issues(
        _CANNED_PROBLEMS, _CANNED_TEST_CASES,
        traj_path=_traj_path(data_dir), out_path=out_path)
    n = len(_CANNED_TEST_CASES)
    ok = reproduced == n and verified == n
    print(f"\n自检结果：{'OK' if ok else 'FAILED'}（复现 {reproduced}/{n}，验证 {verified}/{n}）")
    return 0 if ok else 3


def run_full(model=None, do_github=True, data_dir=DATA,
             out_path=DEFAULT_OUTPUT, create_issue=False):
    """完整流程：真实调用 LLM 诊断并生成回归用例，再重放执行"""
    # 检查 LLM 配置
    try:
        from llm.client import get_llm_client
        client = get_llm_client()
        if not client.api_key:
            print("错误：未配置 LLM API_KEY，请在项目根目录 .env 文件中配置")
            print("（或用 python demo.py --smoke 免 API 自检）")
            sys.exit(1)
    except Exception as e:
        print(f"错误：LLM 配置异常 - {e}")
        print("请确保项目根目录 .env 文件已正确配置")
        sys.exit(1)

    # ---------- 0. 读取输入 ----------
    architecture = _read(data_dir, "architecture.md")
    prd = _read(data_dir, "PRD.md")
    trajectories = list(replay.load_trajectories(_traj_path(data_dir)).values())
    _hr(f"步骤 0｜读取输入：{len(trajectories)} 条生产轨迹 + 架构文档 + PRD")
    for t in trajectories:
        print(f"  - {t['trajectory_id']}: {t['task']}（{len(t['turns'])} 轮）")

    agent = Diagnoser(model=model) if model else Diagnoser()
    print(f"  使用模型：{agent.model}")

    # ---------- 1. 诊断：定位问题 ----------
    _hr("步骤 1｜Agent 诊断（真实调用 LLM）：定位问题并生成结构化报告")
    problems = agent.diagnose(architecture, prd, trajectories)
    if not problems:
        print("未诊断出问题（异常）。")
        sys.exit(2)
    for i, p in enumerate(problems, 1):
        print(f"\n[问题 {i}] {p.get('title', '')}")
        print(f"  优先级 : {p.get('priority')}    模块: {p.get('module')}    PRD: {p.get('prd_ref')}")
        print(f"  轨迹   : {p.get('trajectory_ids')}  关键轮次: {p.get('focus_turns')}")
        print(f"  描述   : {p.get('description')}")
        print(f"  建议   : {p.get('suggestion')}")

    # ---------- 2. 生成回归测试用例 ----------
    _hr("步骤 2｜Agent 生成回归测试用例（真实调用 LLM）：引用轨迹ID + 交互轮次")
    test_cases = agent.gen_test_cases(problems)
    for tc in test_cases:
        print(f"  {tc.get('test_id')}  轨迹={tc.get('trajectory_id')} "
              f"轮次={tc.get('focus_turn')}  断言={json.dumps(tc.get('assertion'), ensure_ascii=False)}")
        print(f"      说明: {tc.get('description')}")

    # ---------- 3/4. 重放执行 + GitHub Issue（默认 mock） ----------
    _replay_and_issues(problems, test_cases, do_github=do_github,
                       traj_path=_traj_path(data_dir), out_path=out_path,
                       create_issue=create_issue)

    _hr("完成｜读轨迹 -> 诊断报告 -> 回归测试用例 -> (mock) GitHub Issue 全流程跑通")


def main():
    parser = argparse.ArgumentParser(
        description="实验 5-8：生产日志的智能诊断系统（读轨迹->诊断->回归测试->GitHub Issue）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  python demo.py                     完整流程（需项目根目录 .env 配置 LLM）\n"
               "  python demo.py --smoke             免 API 快速自检（仅重放+GitHub mock）\n"
               "  python demo.py --model kimi-k3     临时切换模型\n"
               "  python demo.py --data-dir ./mine   换用自己的轨迹/架构/PRD 目录\n"
               "  python demo.py --create-issue      经 MCP 真实创建 Issue（需 GITHUB_TOKEN+GITHUB_REPO）\n"
               "LLM 配置：在项目根目录 .env 文件中设置")
    parser.add_argument("--smoke", action="store_true",
                        help="快速自检：跳过 LLM，用内置样例仅跑重放框架+GitHub mock（无需 API Key）")
    parser.add_argument("--model", default=None,
                        help="临时覆盖模型（默认使用项目配置的模型）")
    parser.add_argument("--data-dir", default=DATA, metavar="DIR",
                        help="输入目录：轨迹日志 trajectories.jsonl + architecture.md + PRD.md（默认 data/）")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, metavar="FILE",
                        help="GitHub Issue（mock）落盘路径（默认 output/github_issues.json）")
    parser.add_argument("--create-issue", action="store_true",
                        help="经 MCP 在真实仓库创建 Issue（需 GITHUB_TOKEN 与 GITHUB_REPO；默认 mock 不联网）")
    parser.add_argument("--no-github", action="store_true",
                        help="跳过步骤 4（既不 mock 也不创建 GitHub Issue）")
    args = parser.parse_args()

    if args.smoke:
        sys.exit(run_smoke(data_dir=args.data_dir, out_path=args.output))
    run_full(model=args.model, do_github=not args.no_github,
             data_dir=args.data_dir, out_path=args.output,
             create_issue=args.create_issue)


if __name__ == "__main__":
    main()
