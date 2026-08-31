#!/usr/bin/env python3
"""固定版本 Stanford Generative Agents 实验的断点续跑运行器。

负责准备共享历史种子、按 360 步（一个虚拟小时）为粒度推进三个实验臂，
并在每个 checkpoint 处持久化模拟状态与压缩的提供商调用回执。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Callable

# 上游官方仓库的固定 commit（实验可复现性的根基）
SOURCE_COMMIT = "fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4"
# 上游自带的 25 人 Smallville 基础环境
BASE_SIM = "base_the_ville_n25"
# 共享历史种子的模拟名（三个实验臂都从它分叉）
SEED_SIM = "exp10_5_history_seed"
# 目标步数：17280 步 = 10 秒/步 × 2 个虚拟日
TARGET_STEPS = 17_280
# 每个 checkpoint 的默认步数（一个虚拟小时）
DEFAULT_CHUNK_STEPS = 360
# 三个实验臂：原始目标 / 替换目标 / 关闭反思
ARMS = ("baseline", "custom_goal", "no_reflection")

# custom_goal 臂注入 Isabella 的替换种子目标。
# 注意：该文本是绑定英文 Smallville 上游环境的实验种子数据（地点、时间
# 均为上游事实），与分析关键词和验收门保持一致，因此保留英文原文。
CUSTOM_CURRENTLY = (
    "Isabella Rodriguez is organizing a community climate-resilience workshop "
    "at Hobbs Cafe on February 14th, 2023, from 5pm to 7pm. She is gathering "
    "workshop materials, recruiting helpers, and inviting everyone she meets."
)
# 上游任务分解提示词的标记与解析正则（兼容层据此识别该类调用）
TASK_DECOMP_MARKER = "Describe subtasks in 5 min increments."
TASK_DECOMP_DURATION = re.compile(r"\(duration in minutes:\s*(\d+)\s*,")
TASK_DECOMP_TOTAL = re.compile(r"total duration in minutes:?\s*(\d+)")
# 任务分解解析失败的可恢复异常类型
TASK_DECOMP_PARSE_ERRORS = (IndexError, TypeError, ValueError)
# 遗留任务分解助手原本的重试预算
TASK_DECOMP_ATTEMPTS = 5
# 识别"诗意评分"提示词的指令片段（用于保留合法的 0 分）
POIGNANCY_SCALE_INSTRUCTION = "scale of 1 to 10"


class ValidatedZero(int):
    """让解析出的合法 0 分区别于遗留代码的 False 哨兵值。"""

    def __new__(cls) -> "ValidatedZero":
        return super().__new__(cls, 0)

    def __eq__(self, other: object) -> bool:
        # 上游用 ``output == False`` 判定失败，这里放行真实的 0 分
        if other is False:
            return False
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        if other is False:
            return True
        return super().__ne__(other)


def atomic_json(path: Path, value: Any) -> None:
    """原子写入 JSON 文件：先写临时文件再重命名，避免崩溃留下半截状态。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def git_commit(upstream: Path) -> str:
    """读取上游仓库当前的 HEAD commit。"""
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=upstream, text=True
    ).strip()


def configure_imports(upstream: Path, storage: Path, temp_storage: Path) -> None:
    """把上游后端注入导入路径，并通过环境变量下发运行时配置覆盖。"""
    experiment_root = Path(__file__).resolve().parent
    backend = upstream / "reverie" / "backend_server"
    os.environ["GA_MAZE_ASSETS_ROOT"] = str(
        (upstream / "environment" / "frontend_server" / "static_dirs" / "assets").resolve()
    )
    os.environ["GA_STORAGE_ROOT"] = str(storage.resolve())
    os.environ["GA_TEMP_STORAGE_ROOT"] = str(temp_storage.resolve())
    temp_storage.mkdir(parents=True, exist_ok=True)
    # compat/ 位于上游后端之前，用于遮蔽上游 utils.py 中的明文凭据配置
    sys.path.insert(0, str(experiment_root / "compat"))
    sys.path.insert(1, str(backend))
    os.chdir(backend)


def install_provider(receipt_path: Path) -> None:
    """安装提供商适配器：凭据与模型全部来自项目根目录统一配置。"""
    from provider_adapter import install

    install(receipt_path=receipt_path)


def normalize_task_decomp_response(response: str, prompt: str) -> str | None:
    """只保留可解析的时长行，并以请求的总时长为上界。"""

    total_match = TASK_DECOMP_TOTAL.search(prompt)
    if not total_match:
        return None
    expected = int(total_match.group(1))
    accumulated = 0
    rows = []
    # 逐行扫描，丢弃解说文字，按原始顺序保留带时长标注的行
    for line in response.splitlines():
        stripped = line.strip()
        duration_match = TASK_DECOMP_DURATION.search(stripped)
        if not duration_match:
            continue
        rows.append(stripped)
        accumulated += int(duration_match.group(1))
        if accumulated >= expected:
            break
    return "\n".join(rows) if rows else None


def safe_task_decomp_generate(
    request: Callable[[str, dict[str, Any]], str],
    prompt: str,
    parameters: dict[str, Any],
    repeat: int,
    fail_safe: Any,
    validate: Callable[..., Any],
    clean_up: Callable[..., Any],
) -> Any:
    """优先使用原始输出；解析失败时清洗出确定性的任务行。"""

    last_parse_error: BaseException | None = None
    for _ in range(repeat):
        response = request(prompt, parameters)
        # 先按上游原路径验证并清理
        try:
            if validate(response, prompt=prompt):
                return clean_up(response, prompt=prompt)
        except TASK_DECOMP_PARSE_ERRORS as exc:
            last_parse_error = exc
        # 解析失败时尝试确定性清洗，而不是立刻重试
        normalized = normalize_task_decomp_response(response, prompt)
        if normalized and normalized != response:
            try:
                return clean_up(normalized, prompt=prompt)
            except TASK_DECOMP_PARSE_ERRORS as exc:
                last_parse_error = exc
    if last_parse_error is not None:
        raise last_parse_error
    return fail_safe


def install_task_decomp_compat() -> None:
    """修复任务分解解析器的输入，而不修改上游源码。"""

    from persona.prompt_template import gpt_structure, run_gpt_prompt

    current = run_gpt_prompt.safe_generate_response
    # 幂等保护：避免重复包装
    if getattr(current, "_exp10_5_task_decomp_compat", False):
        return

    def guarded(
        prompt: str,
        parameters: dict[str, Any],
        repeat: int = TASK_DECOMP_ATTEMPTS,
        fail_safe_response: Any = "error",
        func_validate: Callable[..., Any] | None = None,
        func_clean_up: Callable[..., Any] | None = None,
        verbose: bool = False,
    ) -> Any:
        # 仅拦截任务分解类提示词，其余调用走上游原路径
        if (
            TASK_DECOMP_MARKER not in prompt
            or func_validate is None
            or func_clean_up is None
        ):
            return current(
                prompt,
                parameters,
                repeat,
                fail_safe_response,
                func_validate,
                func_clean_up,
                verbose,
            )
        return safe_task_decomp_generate(
            gpt_structure.GPT_request,
            prompt,
            parameters,
            repeat,
            fail_safe_response,
            func_validate,
            func_clean_up,
        )

    guarded._exp10_5_task_decomp_compat = True  # type: ignore[attr-defined]
    run_gpt_prompt.safe_generate_response = guarded


def install_validated_zero_compat() -> None:
    """保留通过验证的 0 分诗意评分，而不是当成失败。"""

    from persona.prompt_template import run_gpt_prompt

    current = run_gpt_prompt.ChatGPT_safe_generate_response
    # 幂等保护：避免重复包装
    if getattr(current, "_exp10_5_validated_zero_compat", False):
        return

    def guarded(
        prompt: str,
        example_output: Any,
        special_instruction: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        output = current(
            prompt,
            example_output,
            special_instruction,
            *args,
            **kwargs,
        )
        # 上游把 0 分与失败哨兵混为一谈；这里只在诗意评分场景放行 0 分
        if (
            type(output) is int
            and output == 0
            and POIGNANCY_SCALE_INSTRUCTION in special_instruction
        ):
            return ValidatedZero()
        return output

    guarded._exp10_5_validated_zero_compat = True  # type: ignore[attr-defined]
    run_gpt_prompt.ChatGPT_safe_generate_response = guarded


def set_receipt_path(path: Path) -> None:
    """切换当前 checkpoint 的提供商调用回执文件。"""
    from provider_adapter import RECORDER

    RECORDER.set_path(path)


def load_history(server: Any, history_path: Path) -> dict[str, int]:
    """把上游 25 人关系史 CSV 以耳语（whisper）形式灌入共享种子。"""
    from persona.cognitive_modules.converse import load_history_via_whisper

    whispers: list[list[str]] = []
    with history_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = row["Name"].strip()
            whispers.extend(
                [name, item.strip()]
                for item in row["Whisper"].split(";")
                if item.strip()
            )
    # 灌入期间统一世界时钟，灌入完成后恢复为 None（由服务器接管）
    for persona in server.personas.values():
        persona.scratch.curr_time = server.curr_time
    load_history_via_whisper(server.personas, whispers)
    for persona in server.personas.values():
        persona.scratch.curr_time = None
        memory_dir = (
            Path(os.environ["GA_STORAGE_ROOT"])
            / server.sim_code
            / "personas"
            / persona.name
            / "bootstrap_memory"
            / "associative_memory"
        )
        persona.a_mem.save(str(memory_dir))
    return {
        "rows": len({row[0] for row in whispers}),
        "whispers": len(whispers),
        "thought_nodes": sum(len(p.a_mem.seq_thought) for p in server.personas.values()),
    }


def _load_complete_json(path: Path, failures: "queue.Queue[BaseException]") -> dict:
    """等待并加载一个完整落盘的 JSON 文件（写入方使用原子重命名）。"""
    while True:
        if not failures.empty():
            raise failures.get()
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        time.sleep(0.01)


def drive_frontend(
    storage: Path,
    sim_code: str,
    starting_step: int,
    steps: int,
    failures: "queue.Queue[BaseException]",
) -> None:
    """无头前端：根据每步 movement 生成下一步 environment 状态。"""
    try:
        sim_dir = storage / sim_code
        for step in range(starting_step, starting_step + steps):
            movement = _load_complete_json(sim_dir / "movement" / f"{step}.json", failures)
            current = _load_complete_json(sim_dir / "environment" / f"{step}.json", failures)
            # 把每个人物的移动坐标合并进下一步环境状态
            next_environment = {}
            for name, state in current.items():
                x, y = movement["persona"][name]["movement"]
                next_environment[name] = {"maze": state["maze"], "x": x, "y": y}
            output = sim_dir / "environment" / f"{step + 1}.json"
            temporary = output.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(next_environment, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, output)
    except BaseException as exc:
        failures.put(exc)


def compress_receipt(path: Path) -> Path:
    """把回执 JSONL 压缩为 gzip 并删除原文件，返回压缩后的路径。"""
    target = path.with_suffix(path.suffix + ".gz")
    with path.open("rb") as source, gzip.open(target, "wb", compresslevel=9) as output:
        shutil.copyfileobj(source, output)
    path.unlink()
    return target


def quarantine_artifact(path: Path) -> Path | None:
    """把非规范的尝试产物移到 .failed-* 名字下，不改变其文件格式。"""

    if not path.exists():
        return None
    name = path.name
    for ending in (".jsonl.gz", ".jsonl"):
        if name.endswith(ending):
            stem = name[: -len(ending)]
            target = path.with_name(
                f"{stem}.failed-{time.time_ns()}{ending}"
            )
            path.rename(target)
            return target
    target = path.with_name(f"{name}.failed-{time.time_ns()}")
    path.rename(target)
    return target


def receipt_summary(path: Path) -> dict[str, Any]:
    """统计一个回执文件的调用数、分类、错误、重试、用量与时延。"""
    opener = gzip.open if path.suffix == ".gz" else open
    counts: dict[str, int] = {}
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    calls = errors = 0
    transport_retries = 0
    latency = 0.0
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            calls += 1
            kind = row.get("kind", "unknown")
            counts[kind] = counts.get(kind, 0) + 1
            errors += not row.get("success", False)
            transport_retries += len(row.get("transport_retries") or [])
            latency += float(row.get("latency_seconds", 0))
            response_usage = (row.get("response") or {}).get("usage") or {}
            for key in usage:
                usage[key] += int(response_usage.get(key, 0) or 0)
    return {
        "calls": calls,
        "by_kind": counts,
        "errors": errors,
        "transport_retries": transport_retries,
        "usage": usage,
        "provider_latency_seconds": round(latency, 3),
    }


def validated_receipt_summary(
    receipt_path: Path, correction_path: Path
) -> dict[str, Any]:
    """拒绝其规范回执中含提供商错误的已恢复 checkpoint。"""

    summary = receipt_summary(receipt_path)
    # 含错误的调用意味着该 checkpoint 不能作为规范证据
    if summary["errors"]:
        failed_receipt = quarantine_artifact(receipt_path)
        failed_correction = quarantine_artifact(correction_path)
        raise RuntimeError(
            "提供商错误使 checkpoint 不再是规范证据: "
            f"errors={summary['errors']}, receipt={failed_receipt}, "
            f"compatibility={failed_correction}"
        )
    return summary


def jsonl_rows(path: Path) -> int:
    """统计 JSONL 文件的行数；文件不存在时返回 0。"""
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def ensure_base(upstream: Path, storage: Path) -> None:
    """把上游自带的 25 人基础环境复制进存储目录（幂等）。"""
    source = (
        upstream / "environment" / "frontend_server" / "storage" / BASE_SIM
    )
    target = storage / BASE_SIM
    storage.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copytree(source, target)


def prepare_seed(upstream: Path, output: Path) -> None:
    """准备三个实验臂共用的第 0 步历史种子。"""
    from reverie import ReverieServer

    storage = output / "storage"
    seed_dir = storage / SEED_SIM
    status_path = output / "seed_status.json"
    # 种子已完成时直接回放状态，避免重复灌入
    if status_path.exists() and seed_dir.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if status.get("complete"):
            print(json.dumps(status, indent=2))
            return
    if seed_dir.exists():
        shutil.rmtree(seed_dir)
    receipt_path = output / "receipts" / "seed_history.jsonl"
    if receipt_path.exists():
        # 上一次失败的种子灌入回执移入隔离区
        failed = receipt_path.with_name(
            f"seed_history.failed-{int(time.time())}.jsonl"
        )
        receipt_path.rename(failed)
    set_receipt_path(receipt_path)
    started = time.perf_counter()
    with open(os.devnull, "w") as sink, redirect_stdout(sink):
        server = ReverieServer(BASE_SIM, SEED_SIM)
        history_path = (
            upstream
            / "environment"
            / "frontend_server"
            / "static_dirs"
            / "assets"
            / "the_ville"
            / "agent_history_init_n25.csv"
        )
        history = load_history(server, history_path)
    compressed = compress_receipt(receipt_path)
    status = {
        "schema_version": 1,
        "experiment": "10-5",
        "complete": True,
        "source_commit": SOURCE_COMMIT,
        "seed_sim": SEED_SIM,
        "personas": len(server.personas),
        "step": server.step,
        "current_time": server.curr_time.isoformat(),
        "history": history,
        "receipt": str(compressed.relative_to(output)),
        "receipt_summary": receipt_summary(compressed),
        "wall_seconds": round(time.perf_counter() - started, 3),
    }
    atomic_json(status_path, status)
    print(json.dumps(status, indent=2))


def configure_arm(server: Any, arm: str, starting_step: int) -> None:
    """在第 0 步为不同实验臂施加各自的实验处理。"""
    # custom_goal 臂：只在分叉点替换 Isabella 的初始目标
    if arm == "custom_goal" and starting_step == 0:
        server.personas["Isabella Rodriguez"].scratch.currently = CUSTOM_CURRENTLY
    if arm == "no_reflection":
        # no_reflection 臂：禁用反思并防御性调高重要性触发阈值
        from persona.persona import Persona

        Persona.reflect = lambda self: None
        for persona in server.personas.values():
            persona.scratch.importance_trigger_max = 1_000_000_000
            persona.scratch.importance_trigger_curr = 1_000_000_000


def run_arm(
    upstream: Path,
    output: Path,
    arm: str,
    target_steps: int,
    chunk_steps: int,
    max_chunks: int | None,
) -> None:
    """推进单个实验臂：分叉共享种子并按 checkpoint 断点续跑。"""
    from reverie import ReverieServer
    from action_arena_compat import install as install_action_arena_compat

    # 安装全部运行时兼容层
    correction_recorder = install_action_arena_compat()
    install_task_decomp_compat()
    install_validated_zero_compat()

    seed_status = json.loads((output / "seed_status.json").read_text(encoding="utf-8"))
    if not seed_status.get("complete"):
        raise RuntimeError("历史种子未完成")
    storage = output / "storage"
    status_path = output / "status" / f"{arm}.json"
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
    else:
        status = {
            "schema_version": 1,
            "experiment": "10-5",
            "source_commit": SOURCE_COMMIT,
            "arm": arm,
            "personas": 25,
            "target_steps": target_steps,
            "sec_per_step": 10,
            "current_sim": SEED_SIM,
            "completed_steps": 0,
            "checkpoints": [],
            "complete": False,
        }
    chunks_this_run = 0
    while status["completed_steps"] < target_steps:
        # 本次进程允许的最大 chunk 数（用于监督器的定时回收）
        if max_chunks is not None and chunks_this_run >= max_chunks:
            break
        start_step = int(status["completed_steps"])
        steps = min(chunk_steps, target_steps - start_step)
        end_step = start_step + steps
        sim_code = f"exp10_5_{arm}_{end_step:05d}"
        target_dir = storage / sim_code
        # 目标目录存在说明上一次尝试残留，直接清除
        if target_dir.exists():
            shutil.rmtree(target_dir)
        receipt_path = output / "receipts" / arm / f"steps_{start_step:05d}_{end_step:05d}.jsonl"
        # 上一次尝试的回执移入隔离区
        quarantine_artifact(receipt_path)
        quarantine_artifact(receipt_path.with_suffix(receipt_path.suffix + ".gz"))
        correction_path = (
            output
            / "compatibility"
            / arm
            / f"steps_{start_step:05d}_{end_step:05d}.jsonl"
        )
        quarantine_artifact(correction_path)
        set_receipt_path(receipt_path)
        correction_recorder.set_path(correction_path)
        started = time.perf_counter()
        failures: "queue.Queue[BaseException]" = queue.Queue()
        with open(os.devnull, "w") as sink, redirect_stdout(sink):
            server = ReverieServer(status["current_sim"], sim_code)
            (target_dir / "movement").mkdir(exist_ok=True)
            # 分叉后的步数必须精确衔接上一个 checkpoint
            if server.step != start_step:
                raise RuntimeError(
                    f"checkpoint 步数不一致：期望 {start_step}，实际 {server.step}"
                )
            configure_arm(server, arm, start_step)
            # 加速世界时钟推进
            server.server_sleep = 0.001
            controller = threading.Thread(
                target=drive_frontend,
                args=(storage, sim_code, start_step, steps, failures),
                daemon=True,
            )
            controller.start()
            server.start_server(steps)
            controller.join(timeout=30)
            if controller.is_alive():
                raise RuntimeError("无头前端控制器未在超时内完成")
            if not failures.empty():
                raise failures.get()
            server.save()
        compressed = compress_receipt(receipt_path)
        provider_summary = validated_receipt_summary(compressed, correction_path)
        checkpoint = {
            "start_step": start_step,
            "end_step": end_step,
            "start_time": (server.curr_time - dt.timedelta(seconds=10 * steps)).isoformat(),
            "end_time": server.curr_time.isoformat(),
            "sim_code": sim_code,
            "receipt": str(compressed.relative_to(output)),
            "receipt_summary": provider_summary,
            "compatibility_receipt": (
                str(correction_path.relative_to(output))
                if correction_path.exists()
                else None
            ),
            "compatibility_corrections": jsonl_rows(correction_path),
            "wall_seconds": round(time.perf_counter() - started, 3),
        }
        previous_sim = status["current_sim"]
        status["current_sim"] = sim_code
        status["completed_steps"] = end_step
        status["checkpoints"].append(checkpoint)
        status["complete"] = end_step == target_steps
        # 状态文件只有在模拟状态与回执都持久化之后才原子更新
        atomic_json(status_path, status)
        # 清理已被取代的上一小时存储副本（第 0 步分叉与第 8640 步天数边界保留）
        if previous_sim not in {SEED_SIM, BASE_SIM} and start_step != 8_640:
            previous_dir = storage / previous_sim
            if previous_dir.exists():
                shutil.rmtree(previous_dir)
        chunks_this_run += 1
        print(json.dumps(checkpoint, ensure_ascii=False), flush=True)
    print(json.dumps(status, indent=2, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="固定版本 Generative Agents 实验运行器")
    parser.add_argument("--upstream", type=Path, required=True, help="上游官方仓库路径")
    parser.add_argument("--output", type=Path, required=True, help="实验输出目录")
    parser.add_argument("--mode", choices=("seed", "arm"), required=True, help="运行模式：准备种子或推进实验臂")
    parser.add_argument("--arm", choices=ARMS, help="要推进的实验臂")
    parser.add_argument("--target-steps", type=int, default=TARGET_STEPS, help="目标步数")
    parser.add_argument("--chunk-steps", type=int, default=DEFAULT_CHUNK_STEPS, help="每个 checkpoint 的步数")
    parser.add_argument("--max-chunks", type=int, help="本次进程最多推进的 checkpoint 数")
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    output = args.output.resolve()
    # 上游必须精确固定在预注册的 commit 上
    if git_commit(upstream) != SOURCE_COMMIT:
        raise SystemExit(f"上游仓库必须固定在 {SOURCE_COMMIT}")
    output.mkdir(parents=True, exist_ok=True)
    storage = output / "storage"
    temp_storage = output / "temp" / (args.arm or "seed")
    ensure_base(upstream, storage)
    configure_imports(upstream, storage, temp_storage)
    initial_receipt = output / "receipts" / "bootstrap.jsonl"
    install_provider(initial_receipt)
    if args.mode == "seed":
        prepare_seed(upstream, output)
    else:
        if not args.arm:
            parser.error("--mode arm 时必须提供 --arm")
        run_arm(
            upstream,
            output,
            args.arm,
            args.target_steps,
            args.chunk_steps,
            args.max_chunks,
        )
    # 没有实际调用的引导回执文件直接删除
    if initial_receipt.exists() and initial_receipt.stat().st_size == 0:
        initial_receipt.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
