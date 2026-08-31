#!/usr/bin/env python3
"""对 baseline 与消融臂执行臂序盲评的合理性评审。

评审模型只拿到无标签的 A/B 两份轨迹，按四个维度独立打分并给出偏好。
LLM 调用统一走项目根目录 .env 配置的封装客户端，本目录不存放任何密钥。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

# 添加项目根目录到路径，确保可以导入统一的 LLM 封装模块
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from llm.client import get_llm_client

# 评审维度（键名保持英文，作为数据模式的一部分参与持久化与验收）
DIMENSIONS = (
    "temporal_coherence",
    "personality_consistency",
    "memory_continuity",
    "social_responsiveness",
)
# 单次评审请求的客户端超时（秒）
JUDGE_TIMEOUT_SECONDS = 180


def load_json(path: Path) -> Any:
    """读取并解析 JSON 文件。"""
    return json.loads(path.read_text(encoding="utf-8"))


def evenly_sample(rows: list[Any], maximum: int) -> list[Any]:
    """在保留首尾的前提下等距采样至最多 maximum 条。"""
    if len(rows) <= maximum:
        return rows
    if maximum == 1:
        return [rows[0]]
    indexes = {
        round(index * (len(rows) - 1) / (maximum - 1)) for index in range(maximum)
    }
    return [rows[index] for index in sorted(indexes)]


def seed_node_counts(output: Path) -> dict[str, int]:
    """统计共享历史种子里每个人物的记忆节点数（作为新记忆的基线）。"""
    seed = output / "storage" / "exp10_5_history_seed" / "personas"
    result = {}
    for persona in seed.iterdir():
        if persona.is_dir():
            nodes = load_json(
                persona
                / "bootstrap_memory"
                / "associative_memory"
                / "nodes.json"
            )
            result[persona.name] = len(nodes)
    return result


def build_trace(output: Path, arm: str, persona: str, seed_count: int) -> dict:
    """从某个实验臂的最终状态提取某个人物的可评审轨迹。"""
    status = load_json(output / "status" / f"{arm}.json")
    sim = output / "storage" / status["current_sim"]
    scratch = load_json(
        sim / "personas" / persona / "bootstrap_memory" / "scratch.json"
    )
    nodes = load_json(
        sim
        / "personas"
        / persona
        / "bootstrap_memory"
        / "associative_memory"
        / "nodes.json"
    )
    # 只保留种子之后新增的记忆（超出种子计数的节点）
    new_memories = [
        {
            "created": row.get("created"),
            "type": row.get("type"),
            "depth": row.get("depth"),
            "description": row.get("description"),
            "evidence_count": len(row.get("filling") or []),
        }
        for row in nodes.values()
        if int(row.get("node_count", 0)) > seed_count
    ]
    # 抽取动作发生变化的时间点（动作转移序列）
    transitions = []
    previous = None
    meta = load_json(sim / "reverie" / "meta.json")
    for step in range(int(meta["step"])):
        movement = load_json(sim / "movement" / f"{step}.json")
        description = str(movement["persona"][persona].get("description", ""))
        if description != previous:
            transitions.append(
                {
                    "time": movement["meta"]["curr_time"],
                    "action": description,
                }
            )
            previous = description
    return {
        "profile": {
            "name": scratch.get("name"),
            "innate_traits": scratch.get("innate"),
            "learned_traits": scratch.get("learned"),
            "initial_or_current_goal": scratch.get("currently"),
            "lifestyle": scratch.get("lifestyle"),
            "daily_plan_requirement": scratch.get("daily_plan_req"),
        },
        "action_transitions": evenly_sample(transitions, 40),
        "memory_stream_sample": evenly_sample(new_memories, 32),
        "counts": {
            "action_transitions": len(transitions),
            "new_memories": len(new_memories),
            "new_thoughts": sum(row["type"] == "thought" for row in new_memories),
            "evidence_linked_thoughts": sum(
                row["type"] == "thought" and row["evidence_count"] > 0
                for row in new_memories
            ),
        },
    }


def make_prompt(persona: str, trace_a: dict, trace_b: dict) -> str:
    """构造臂序盲评提示词：评审只依据给定证据，不得猜测期望赢家。"""
    rubric = {
        "temporal_coherence": "动作构成可行且不自相矛盾的两天序列。",
        "personality_consistency": "动作始终与给定的人格特质、生活方式和目标保持一致。",
        "memory_continuity": "后续记忆/动作连贯地利用了先前经历，而不是表现为互不相关的孤立片段。",
        "social_responsiveness": "当出现他人或社交信息时，人物能连贯地作出反应；不要仅因轨迹中遭遇较少而扣分。",
    }
    schema = {
        "A": {dimension: 1 for dimension in DIMENSIONS},
        "B": {dimension: 1 for dimension in DIMENSIONS},
        "preferred": "A, B, or tie",
        "evidence": {
            dimension: ["来自 A 的具体细节", "来自 B 的具体细节"]
            for dimension in DIMENSIONS
        },
        "confidence": "low, medium, or high",
    }
    return (
        "你将评估来自同一模拟人物的两份未标注轨迹。"
        "请对每份轨迹独立打分：1（不可信）到 5（高度可信）。"
        "只依据给定证据评判。不要推断轨迹由哪个系统产生，"
        "不要仅因冗长或记忆数量多而加分，也不要预设期望的赢家。\n\n"
        f"人物：{persona}\n评分标准：\n{json.dumps(rubric, ensure_ascii=False, indent=2)}\n\n"
        f"轨迹 A：\n{json.dumps(trace_a, ensure_ascii=False)}\n\n"
        f"轨迹 B：\n{json.dumps(trace_b, ensure_ascii=False)}\n\n"
        "严格返回一个符合以下形态的 JSON 对象，分数为 1 到 5 的整数（键保持原样）：\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
    )


def parse_json_object(text: str) -> dict:
    """从响应文本中解析并校验评审 JSON 对象。"""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("响应中不包含 JSON 对象")
    value = json.loads(text[start : end + 1])
    # 校验所有维度的分数都是 1 到 5 的整数
    for label in ("A", "B"):
        for dimension in DIMENSIONS:
            score = value[label][dimension]
            if not isinstance(score, int) or not 1 <= score <= 5:
                raise ValueError(f"{label} 的 {dimension} 分数非法: {score!r}")
    if value.get("preferred") not in {"A", "B", "tie"}:
        raise ValueError("preferred 标签非法")
    return value


def call_judge(prompt: str, client: Any, model: str) -> tuple[dict, dict, float]:
    """调用统一配置的 LLM 客户端执行一次评审。

    Returns:
        (请求体, 脱敏后的完整响应字典, 时延秒数) 三元组。
    """
    request_body = {
        "model": model,
        "max_tokens": 1800,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1800,
            temperature=0,
            timeout=JUDGE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        latency = time.perf_counter() - started
        raise RuntimeError(f"评审调用失败（{type(exc).__name__}，{latency:.1f}s）: {str(exc)[:500]}") from exc
    latency = time.perf_counter() - started
    # 现代 SDK 返回 pydantic 模型，统一转为字典供回执留存
    raw = response.model_dump()
    return request_body, raw, latency


def load_canonical_judgments(receipts_path: Path) -> list[dict]:
    """保留失败的评审尝试作为证据，但不混入规范评审行。"""

    if not receipts_path.exists():
        return []
    rows = [json.loads(line) for line in receipts_path.read_text(encoding="utf-8").splitlines() if line]
    failed = [row for row in rows if not row.get("success")]
    if not failed:
        return rows
    # 把失败行移入 .failed-* 文件，原文件只保留成功行
    failed_path = receipts_path.with_name(
        f"{receipts_path.stem}.failed-{time.time_ns()}{receipts_path.suffix}"
    )
    failed_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in failed),
        encoding="utf-8",
    )
    successful = [row for row in rows if row.get("success")]
    receipts_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in successful),
        encoding="utf-8",
    )
    return successful


def main() -> int:
    parser = argparse.ArgumentParser(description="臂序盲评的合理性评审运行器")
    parser.add_argument("output", type=Path, help="实验输出目录")
    parser.add_argument("--model", default=None, help="评审模型名（默认取统一配置的 LLM_MODEL）")
    parser.add_argument("--limit", type=int, help="最多评审的人物数")
    args = parser.parse_args()
    output = args.output.resolve()
    # 统一客户端：凭据与端点只来自项目根目录 .env
    client = get_llm_client()
    model = args.model or client.model_name
    counts = seed_node_counts(output)
    personas = sorted(counts)
    if args.limit is not None:
        personas = personas[: args.limit]
    analysis = output / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    receipts_path = analysis / "plausibility_judgments.jsonl"
    rows = load_canonical_judgments(receipts_path)
    completed = {row["persona"] for row in rows}
    for persona in personas:
        # 已有规范评审行的人物跳过，保证可断点重跑
        if persona in completed:
            continue
        baseline = build_trace(output, "baseline", persona, counts[persona])
        ablation = build_trace(output, "no_reflection", persona, counts[persona])
        # 按人物名的哈希决定 A/B 臂序，评审者无法据此反推
        baseline_is_a = hashlib.sha256(persona.encode()).digest()[0] % 2 == 0
        trace_a, trace_b = (baseline, ablation) if baseline_is_a else (ablation, baseline)
        prompt = make_prompt(persona, trace_a, trace_b)
        try:
            request_body, response, latency = call_judge(prompt, client, model)
            text = response["choices"][0]["message"]["content"]
            judgment = parse_json_object(text)
            row = {
                "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "persona": persona,
                "baseline_label": "A" if baseline_is_a else "B",
                "request": request_body,
                "response": response,
                "latency_seconds": round(latency, 3),
                "judgment": judgment,
                "success": True,
                "error": None,
            }
        except Exception as exc:
            # 失败行只留存提示词哈希，避免重复写入超长提示词
            row = {
                "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "persona": persona,
                "baseline_label": "A" if baseline_is_a else "B",
                "request": {"model": model, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()},
                "response": None,
                "latency_seconds": None,
                "judgment": None,
                "success": False,
                "error": {"type": type(exc).__name__, "message": str(exc)[:1000]},
            }
        if not row["success"]:
            failed_path = receipts_path.with_name(
                f"{receipts_path.stem}.failed-{time.time_ns()}{receipts_path.suffix}"
            )
            failed_path.write_text(
                json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            raise RuntimeError(row["error"])
        with receipts_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        rows.append(row)

    # 汇总：按维度做基线/消融的配对均值，并统计偏好
    successful = [row for row in rows if row.get("success") and row["persona"] in personas]
    paired = {dimension: {"baseline": [], "no_reflection": []} for dimension in DIMENSIONS}
    preferences = {"baseline": 0, "no_reflection": 0, "tie": 0}
    for row in successful:
        baseline_label = row["baseline_label"]
        ablation_label = "B" if baseline_label == "A" else "A"
        for dimension in DIMENSIONS:
            paired[dimension]["baseline"].append(row["judgment"][baseline_label][dimension])
            paired[dimension]["no_reflection"].append(row["judgment"][ablation_label][dimension])
        preferred = row["judgment"]["preferred"]
        if preferred == "tie":
            preferences["tie"] += 1
        elif preferred == baseline_label:
            preferences["baseline"] += 1
        else:
            preferences["no_reflection"] += 1
    summary = {
        "schema_version": 1,
        "experiment": "10-5",
        "model": model,
        "judgments": len(successful),
        "preferences": preferences,
        "mean_scores": {
            dimension: {
                arm: statistics.mean(values) if values else None
                for arm, values in arms.items()
            }
            for dimension, arms in paired.items()
        },
        "raw_receipts": str(receipts_path.relative_to(output)),
    }
    (analysis / "plausibility_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    , encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
