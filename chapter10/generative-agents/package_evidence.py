#!/usr/bin/env python3
"""生成紧凑、完整、可复核的实验 10-5 证据包。"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# 添加项目根目录到路径，确保可以导入统一的 LLM 封装模块
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from llm.client import get_llm_config


ARMS = ("baseline", "custom_goal", "no_reflection")
# 上游官方仓库的固定 commit（与运行器保持一致）
SOURCE_COMMIT = "fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4"


def load_json(path: Path):
    """读取并解析 JSON 文件。"""
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    """计算文件的内容哈希。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_json(source: Path, target: Path) -> None:
    """复制 JSON 文件并保留元数据。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def export_state(sim: Path, destination: Path) -> None:
    """导出一个模拟目录的最终状态：元数据、scratch、记忆与全部移动流。"""
    destination.mkdir(parents=True, exist_ok=True)
    meta = load_json(sim / "reverie" / "meta.json")
    copy_json(sim / "reverie" / "meta.json", destination / "meta.json")
    copy_json(
        sim / "environment" / f"{meta['step']}.json",
        destination / "final_environment.json",
    )
    scratch = {}
    # 记忆节点逐人物压缩写入 JSONL，避免巨型 JSON
    memory_path = destination / "memory_nodes.jsonl.gz"
    with gzip.open(memory_path, "wt", encoding="utf-8", compresslevel=9) as memory:
        for persona in sorted(meta["persona_names"]):
            root = sim / "personas" / persona / "bootstrap_memory"
            scratch[persona] = load_json(root / "scratch.json")
            nodes = load_json(root / "associative_memory" / "nodes.json")
            for node_id, node in nodes.items():
                memory.write(
                    json.dumps(
                        {"persona": persona, "node_id": node_id, "node": node},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
    (destination / "scratch.json").write_text(
        json.dumps(scratch, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # 全部步数的移动记录同样压缩为 JSONL
    movements_path = destination / "movements.jsonl.gz"
    with gzip.open(movements_path, "wt", encoding="utf-8", compresslevel=9) as output:
        for step in range(int(meta["step"])):
            movement = load_json(sim / "movement" / f"{step}.json")
            output.write(
                json.dumps(
                    {"step": step, "movement": movement},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="实验证据打包器")
    parser.add_argument("output", type=Path, help="实验输出目录")
    parser.add_argument("destination", type=Path, help="证据包目标目录")
    parser.add_argument("--upstream", type=Path, required=True, help="上游官方仓库路径")
    args = parser.parse_args()
    output = args.output.resolve()
    destination = args.destination.resolve()
    # 目标目录必须不存在，避免覆盖既有证据包
    if destination.exists():
        raise SystemExit(f"目标目录已存在: {destination}")
    statuses = {
        arm: load_json(output / "status" / f"{arm}.json") for arm in ARMS
    }
    if not all(status.get("complete") for status in statuses.values()):
        raise SystemExit("三个实验臂必须全部完成后才能打包")
    for required in (
        output / "analysis" / "deterministic_analysis.json",
        output / "analysis" / "plausibility_judgments.jsonl",
        output / "analysis" / "plausibility_summary.json",
    ):
        if not required.exists():
            raise SystemExit(f"缺少分析产物: {required}")
    destination.mkdir(parents=True)
    experiment_root = Path(__file__).resolve().parent
    copy_json(experiment_root / "experiment_protocol.json", destination / "protocol.json")
    copy_json(output / "seed_status.json", destination / "seed_status.json")
    for arm in ARMS:
        copy_json(output / "status" / f"{arm}.json", destination / "status" / f"{arm}.json")
        sim = output / "storage" / statuses[arm]["current_sim"]
        export_state(sim, destination / "states" / arm)
    shutil.copytree(output / "receipts", destination / "receipts")
    compatibility = output / "compatibility"
    if not compatibility.is_dir():
        raise SystemExit("缺少行动场所兼容性回执")
    shutil.copytree(compatibility, destination / "compatibility")
    shutil.copytree(output / "analysis", destination / "analysis")
    upstream_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=args.upstream, text=True
    ).strip()
    upstream_status = subprocess.check_output(
        ["git", "status", "--short"], cwd=args.upstream, text=True
    ).splitlines()
    # 实验环境的模型名从统一配置解析（与运行时一致）
    config = get_llm_config()
    chat_model = os.environ.get("CHAPTER10_CHAT_MODEL") or config["model"]
    embedding_model = os.environ.get("CHAPTER10_EMBEDDING_MODEL", "text-embedding-v4")
    environment = {
        "schema_version": 1,
        "experiment": "10-5",
        "source_commit": upstream_commit,
        "source_clean": not upstream_status,
        "source_status": upstream_status,
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "chat_model": chat_model,
        "embedding_model": embedding_model,
        # 凭据一律来自统一 .env 的 API_KEY，永不落盘
        "credential_environment_variables": ["API_KEY"],
    }
    (destination / "environment.json").write_text(
        json.dumps(environment, indent=2) + "\n", encoding="utf-8"
    )
    # 打包过程中上游 commit 变化说明证据链被破坏，直接中止
    if upstream_commit != SOURCE_COMMIT:
        raise SystemExit("打包过程中上游 commit 发生了变化")
    files = []
    for path in sorted(item for item in destination.rglob("*") if item.is_file()):
        if path.name in {"acceptance.json", "manifest.json"}:
            continue
        files.append(
            {
                "path": str(path.relative_to(destination)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    manifest = {
        "schema_version": 1,
        "experiment": "10-5",
        "run_id": destination.name,
        "files": files,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"destination": str(destination), "files": len(files)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
