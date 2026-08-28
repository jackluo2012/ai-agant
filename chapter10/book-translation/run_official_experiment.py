#!/usr/bin/env python3
"""实验 10-2 官方全量验收战役：在真实的图文并茂、含大量代码的技术书上运行。

sample_book/ 内置的四章短书适合低成本入门演示；本脚本面向正式验收：
翻译输入的各章 Markdown（默认取内置样书前两章，可通过 --source 指定任意章节），
对比“四角色管理者工作流”与“单 Agent 累积对话”两种方式，并保存质量、耗时、
上下文规模、token 消耗与数据来源（provenance）证据。

使用示例:
    python run_official_experiment.py                     # 默认翻译样书前两章
    python run_official_experiment.py --source path/ch1.md --source path/ch2.md
"""

from __future__ import annotations

# 添加项目根目录到路径（统一 LLM 配置位于 ai-agant 根目录）
import sys
import os
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_here_dir = os.path.dirname(os.path.abspath(__file__))
if _here_dir not in sys.path:
    sys.path.insert(0, _here_dir)

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from llm.client import get_llm_client
except ImportError:
    get_llm_client = None

HERE = Path(__file__).parent
REPO = HERE.parents[1]
# 默认输入：项目内置样书的前两章（可用 --source 反复传入覆盖）
DEFAULT_SOURCES = (HERE / "sample_book" / "chapter1.md", HERE / "sample_book" / "chapter2.md")
DIMENSIONS = ("accuracy", "fluency", "terminology", "markdown_code_fidelity")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def load_source_book(paths: list[Path]) -> tuple[dict[str, str], dict[str, str]]:
    """读取各章 Markdown，返回 {章节标题: 原文} 与 {章节标题: 相对路径}。"""
    chapters: dict[str, str] = {}
    title_to_path: dict[str, str] = {}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        title = extract_title(text, path.stem)
        # 章节标题作为全流程的键，重复会导致结果互相覆盖
        if title in chapters:
            raise ValueError(f"输入章节标题重复：{title}")
        chapters[title] = text
        title_to_path[title] = str(path.relative_to(REPO))
    return chapters, title_to_path


def markdown_blocks(text: str) -> list[str]:
    """按空行切块；绝不从围栏代码块中间切开。"""
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        current.append(line)
        if not in_fence and not line.strip():
            blocks.append("".join(current))
            current = []
    if current:
        blocks.append("".join(current))
    return blocks


def split_translation_units(
    chapters: dict[str, str], max_characters: int = 36_000
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """把超长章节切成有界翻译单元，同时保留可精确重组回原文的映射。"""
    units: dict[str, str] = {}
    chapter_units: dict[str, list[str]] = {}
    for title, text in chapters.items():
        parts: list[str] = []
        current = ""
        for block in markdown_blocks(text):
            if current and len(current) + len(block) > max_characters:
                parts.append(current)
                current = ""
            if len(block) > max_characters:
                # 罕见的超大普通文本块：按行边界切分；
                # 围栏代码块是一个不可分割的整体——刻意允许其超过目标大小而不截断。
                if block.lstrip().startswith("```"):
                    if current:
                        parts.append(current)
                        current = ""
                    parts.append(block)
                    continue
                for line in block.splitlines(keepends=True):
                    if current and len(current) + len(line) > max_characters:
                        parts.append(current)
                        current = ""
                    current += line
            else:
                current += block
        if current:
            parts.append(current)
        names = []
        for index, part in enumerate(parts, start=1):
            name = f"{title} [Part {index}/{len(parts)}]"
            units[name] = part
            names.append(name)
        chapter_units[title] = names
        # 切分必须无损：拼回来必须与原文字节一致，否则说明切法有 bug
        if "".join(parts) != text:
            raise AssertionError(f"翻译单元切分改变了 {title} 的源字节")
    return units, chapter_units


def reassemble_translations(
    translations: dict[str, str], chapter_units: dict[str, list[str]]
) -> dict[str, str]:
    """按记录的单元顺序重组各章完整译文。"""
    return {
        chapter: "\n\n".join(translations[unit].rstrip() for unit in units).rstrip() + "\n"
        for chapter, units in chapter_units.items()
    }


def fenced_code_payloads(text: str) -> list[str]:
    return re.findall(r"^```[^\n]*\n(.*?)^```[ \t]*$", text, flags=re.MULTILINE | re.DOTALL)


def image_targets(text: str) -> list[str]:
    return re.findall(r"!\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", text)


def link_targets(text: str) -> list[str]:
    return re.findall(r"(?<!!)\[[^\]]+\]\(([^\s)]+)(?:\s+[^)]*)?\)", text)


def markdown_fidelity(source: str, translation: str) -> dict[str, Any]:
    source_code = fenced_code_payloads(source)
    translated_code = fenced_code_payloads(translation)
    source_images = image_targets(source)
    translated_images = image_targets(translation)
    source_links = link_targets(source)
    translated_links = link_targets(translation)
    source_headings = len(re.findall(r"^#{1,6}\s+", source, flags=re.MULTILINE))
    translated_headings = len(re.findall(r"^#{1,6}\s+", translation, flags=re.MULTILINE))
    return {
        "source_sha256": sha256_text(source),
        "translation_sha256": sha256_text(translation),
        "nonempty_translation": bool(translation.strip()),
        "character_ratio": len(translation) / len(source) if source else 0.0,
        "fenced_code": {
            "source_count": len(source_code),
            "translation_count": len(translated_code),
            "exact_payload_sequence_preserved": source_code == translated_code,
        },
        "images": {
            "source_count": len(source_images),
            "translation_count": len(translated_images),
            "exact_target_sequence_preserved": source_images == translated_images,
        },
        "links": {
            "source_count": len(source_links),
            "translation_count": len(translated_links),
            "exact_target_sequence_preserved": source_links == translated_links,
        },
        "headings": {
            "source_count": source_headings,
            "translation_count": translated_headings,
            "count_preserved": source_headings == translated_headings,
        },
    }


def validate_judge_response(payload: dict[str, Any]) -> dict[str, Any]:
    """严格校验评审模型返回的 JSON 结构，不合格即抛 ValueError。

    Args:
        payload: 评审模型输出的原始 JSON 对象

    Returns:
        归一化后的校验通过字典（含可选的 schema_repairs 记录）

    Raises:
        ValueError: 结构缺失、字段类型错误或证据为空时
    """
    payload = dict(payload)
    variants = payload.get("variants")
    repairs: list[str] = []
    # 无损结构修复：个别模型会把 preferred / preference_evidence 多嵌套一层到
    # variants 里，而 X/Y 评分本体完整。此时把它们上提一层即可；
    # 其余任意多余键或残缺评分仍视为硬失败。
    if isinstance(variants, dict) and {"X", "Y"}.issubset(variants):
        extras = set(variants) - {"X", "Y"}
        if extras and extras.issubset({"preferred", "preference_evidence"}):
            for key in extras:
                if key not in payload:
                    payload[key] = variants[key]
            variants = {alias: variants[alias] for alias in ("X", "Y")}
            repairs.append("已把嵌套在 variants 中的偏好字段上提到顶层")
    if not isinstance(variants, dict) or set(variants) != {"X", "Y"}:
        raise ValueError("评审结果必须恰好包含 X 与 Y 两个变体")
    normalized: dict[str, Any] = {"variants": {}}
    for alias in ("X", "Y"):
        variant = variants[alias]
        if not isinstance(variant, dict) or set(variant) != set(DIMENSIONS):
            raise ValueError(f"评审变体 {alias} 必须包含全部四个评分维度")
        normalized["variants"][alias] = {}
        for dimension in DIMENSIONS:
            item = variant[dimension]
            if not isinstance(item, dict):
                raise ValueError(f"{alias}.{dimension} 必须是对象")
            score, evidence = item.get("score"), item.get("evidence")
            if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
                raise ValueError(f"{alias}.{dimension}.score 必须是 1 到 5 的整数")
            if not isinstance(evidence, str) or not evidence.strip():
                raise ValueError(f"{alias}.{dimension}.evidence 必须是非空字符串")
            normalized["variants"][alias][dimension] = {
                "score": score, "evidence": evidence.strip(),
            }
    preferred = payload.get("preferred")
    if preferred not in ("X", "Y", "tie"):
        raise ValueError("评审的 preferred 必须是 X、Y 或 tie")
    reason = payload.get("preference_evidence")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("评审的 preference_evidence 必须是非空字符串")
    normalized.update(preferred=preferred, preference_evidence=reason.strip())
    if repairs:
        normalized["schema_repairs"] = repairs
    return normalized


def _parse_json(text: str) -> dict[str, Any]:
    """解析模型输出：容忍 Markdown 代码围栏；非对象 JSON 直接报错。"""
    value = (text or "").strip()
    if value.startswith("```"):
        lines = value.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines.pop()
        value = "\n".join(lines)
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("评审返回的不是 JSON 对象")
    return payload


def make_judge() -> tuple[Any, str, str]:
    """创建质量评审客户端（统一使用项目根目录 .env 的 LLM 配置）。

    Returns:
        (客户端实例, 模型名, 提供商标签)

    Raises:
        RuntimeError: llm 模块不可导入时
        ValueError: 根目录 .env 缺少必要配置时
    """
    if get_llm_client is None:
        raise RuntimeError(
            "质量评审依赖统一 LLM 客户端 llm.client，"
            "请确认在项目根目录 ai-agant 下运行。"
        )
    judge_client = get_llm_client()
    return judge_client, judge_client.model_name, judge_client.provider


def judge_chapter(
    client,
    model: str,
    source: str,
    x_translation: str,
    y_translation: str,
    receipt_path: Path | None = None,
    max_attempts: int = 4,
) -> tuple[dict[str, Any], dict[str, int]]:
    """用盲评方式对比同一章节的两份匿名中文译文。

    Args:
        client: 统一 LLM 客户端
        model: 评审使用的模型名
        source: 英文原文全量内容
        x_translation: 匿名译文 X
        y_translation: 匿名译文 Y
        receipt_path: 原始回执落盘路径（支持断点恢复）
        max_attempts: 最大尝试次数

    Returns:
        (归一化评审结果, 用量统计字典)
    """
    # 盲评提示词：按四个维度给两份匿名译文打分，每项评分都必须给出可定位的证据
    prompt = (
        "你是一名严苛的中英双语技术书籍翻译评审。对照完整的英文 Markdown 原文，比较两份匿名"
        "中文译文（分别记为 X 与 Y），并各自在以下四个维度打 1–5 分：accuracy（准确度：无遗漏、"
        "无杜撰、无篡改原意）；fluency（流畅度）；terminology（术语一致且技术上正确）；"
        "markdown_code_fidelity（图片、链接、标题、公式、围栏代码是否原样保留）。每个评分都必须"
        "给出引用原文或明确位置的依据；只有在证据支持时才可偏向某一份。只输出 JSON，格式为："
        '{"variants":{"X":{"accuracy":{"score":1,"evidence":"..."},"fluency":'
        '{"score":1,"evidence":"..."},"terminology":{"score":1,"evidence":"..."},'
        '"markdown_code_fidelity":{"score":1,"evidence":"..."}},"Y":{"accuracy":'
        '{"score":1,"evidence":"..."},"fluency":{"score":1,"evidence":"..."},'
        '"terminology":{"score":1,"evidence":"..."},"markdown_code_fidelity":'
        '{"score":1,"evidence":"..."}}},"preferred":"X|Y|tie",'
        '"preference_evidence":"..."}。\n\n'
        f"英文原文全文：\n{source}\n\n匿名中文译文 X：\n{x_translation}"
        f"\n\n匿名中文译文 Y：\n{y_translation}"
    )
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    def repair_prompt(content: str, error: Exception) -> str:
        """构造 schema 修复提示词：让模型把上次的 JSON 改形为要求结构，而不是重新评审。"""
        return (
            "这是一次格式修复请求，不是重新评审。请把下面的 JSON 整理为要求的精确结构，同时完整保留"
            "每一项评分、每一条证据陈述、偏好结论及其理由。顶层必须包含 variants、preferred 与 "
            "preference_evidence；variants 必须恰好包含 X 与 Y；X 与 Y 各自必须恰好包含 accuracy、"
            "fluency、terminology 与 markdown_code_fidelity 四个维度，且每个维度都包含 score 和 "
            "evidence。不要重新评分、不要重命名字段、不要把 Y 嵌套进 X、也不要新增键。"
            f"上一次校验错误：{error}。只输出 JSON。\n\n"
            f"待修复 JSON：\n{content}"
        )

    attempts: list[dict[str, Any]] = []
    repair_message: str | None = None
    if receipt_path is not None and receipt_path.exists():
        saved = json.loads(receipt_path.read_text(encoding="utf-8"))
        attempts = saved.get("attempts", [])
        if attempts:
            previous = attempts[-1]
            previous_content = previous.get("response", {}).get("content", "")
            try:
                recovered = validate_judge_response(_parse_json(previous_content))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                repair_message = repair_prompt(previous_content, exc)
            else:
                previous["resume_validation"] = {
                    "valid": True,
                    "schema_repairs": recovered.get("schema_repairs", []),
                }
                write_json_atomic(receipt_path, {
                    "schema_version": 1,
                    "credential_free": True,
                    "attempts": attempts,
                })
                return recovered, {
                    "prompt_tokens": sum(
                        row["response"]["usage"]["prompt_tokens"] for row in attempts
                    ),
                    "completion_tokens": sum(
                        row["response"]["usage"]["completion_tokens"] for row in attempts
                    ),
                    "latency_milliseconds": sum(
                        row["latency_milliseconds"] for row in attempts
                    ),
                    "attempt_count": len(attempts),
                }
    prior_attempt_count = len(attempts)
    for retry_number in range(1, max_attempts + 1):
        attempt_number = prior_attempt_count + retry_number
        request = dict(kwargs)
        request["messages"] = (
            [{"role": "user", "content": repair_message}]
            if repair_message is not None else kwargs["messages"]
        )
        started = time.perf_counter()
        try:
            response = client.chat.completions.create(**request)
        except Exception as exc:
            if "temperature" not in str(exc).lower() or "temperature" not in kwargs:
                raise
            kwargs.pop("temperature")
            request.pop("temperature", None)
            response = client.chat.completions.create(**request)
        latency = time.perf_counter() - started
        content = response.choices[0].message.content or ""
        usage = response.usage
        attempt = {
            "attempt": attempt_number,
            "request_kind": "schema_repair" if repair_message is not None else "quality_judgment",
            "request": request,
            "response": {
                "id": getattr(response, "id", None),
                "model": getattr(response, "model", None),
                "created": getattr(response, "created", None),
                "content": content,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": getattr(
                        usage, "total_tokens", usage.prompt_tokens + usage.completion_tokens
                    ),
                },
            },
            "latency_milliseconds": round(latency * 1000),
        }
        try:
            result = validate_judge_response(_parse_json(content))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            attempt["validation"] = {
                "valid": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            attempts.append(attempt)
            if receipt_path is not None:
                write_json_atomic(receipt_path, {
                    "schema_version": 1,
                    "credential_free": True,
                    "attempts": attempts,
                })
            if retry_number == max_attempts:
                raise RuntimeError(
                    f"评审结果在累计 {attempt_number} 次尝试后仍未通过 schema 校验：{exc}"
                ) from exc
            repair_message = repair_prompt(content, exc)
            continue
        attempt["validation"] = {"valid": True}
        attempts.append(attempt)
        if receipt_path is not None:
            write_json_atomic(receipt_path, {
                "schema_version": 1,
                "credential_free": True,
                "attempts": attempts,
            })
        return result, {
            "prompt_tokens": sum(row["response"]["usage"]["prompt_tokens"] for row in attempts),
            "completion_tokens": sum(
                row["response"]["usage"]["completion_tokens"] for row in attempts
            ),
            "latency_milliseconds": sum(row["latency_milliseconds"] for row in attempts),
            "attempt_count": len(attempts),
        }
    raise AssertionError("不可达：评审重试循环应在此前返回或抛错")


def aggregate_judges(chapter_judges: list[dict[str, Any]]) -> dict[str, Any]:
    """按模式聚合全部章节的评审分数与偏好统计。"""
    scores = {
        mode: {dimension: [] for dimension in DIMENSIONS}
        for mode in ("orchestration", "single_agent")
    }
    preferences = {"orchestration": 0, "single_agent": 0, "tie": 0}
    for row in chapter_judges:
        mapping = row["alias_to_mode"]
        result = row["result"]
        for alias, dimensions in result["variants"].items():
            mode = mapping[alias]
            for dimension, item in dimensions.items():
                scores[mode][dimension].append(item["score"])
        preferred = result["preferred"]
        preferences["tie" if preferred == "tie" else mapping[preferred]] += 1
    modes = {}
    for mode, dimensions in scores.items():
        means = {key: sum(values) / len(values) for key, values in dimensions.items()}
        modes[mode] = {"dimension_means": means, "overall_mean": sum(means.values()) / len(means)}
    return {"modes": modes, "chapter_preferences": preferences}


def source_statistics(chapters: dict[str, str]) -> dict[str, Any]:
    """统计输入书籍的规模指标（章节数、字节数、图片 / 代码块 / 链接引用数）。"""
    return {
        "chapter_count": len(chapters),
        "bytes": sum(len(text.encode("utf-8")) for text in chapters.values()),
        "lines": sum(len(text.splitlines()) for text in chapters.values()),
        "image_references": sum(len(image_targets(text)) for text in chapters.values()),
        "fenced_code_blocks": sum(len(fenced_code_payloads(text)) for text in chapters.values()),
        "link_references": sum(len(link_targets(text)) for text in chapters.values()),
    }


def tracker_receipt(tracker) -> dict[str, Any]:
    """把 TokenTracker 序列化为可落盘的记账回执。"""
    return {
        "calls": tracker.calls,
        "by_agent": tracker.by_agent(),
        "total_tokens": tracker.total_tokens(),
    }


def write_json_atomic(path: Path, value: Any) -> None:
    """原子化写入 JSON：先写临时文件再替换，避免留下写了一半的检查点。"""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def serialize_arm(result: dict[str, Any]) -> dict[str, Any]:
    """把 agents.py 某一运行方式（arm）的结果序列化为可续跑的检查点 JSON。"""
    return {
        **{key: value for key, value in result.items() if key != "tracker"},
        "tracker_calls": result["tracker"].calls,
    }


def restore_arm(payload: dict[str, Any], agents_module: Any) -> dict[str, Any]:
    """从检查点 JSON 还原某一运行方式的结果（重建 TokenTracker）。"""
    value = dict(payload)
    calls = value.pop("tracker_calls")
    tracker = agents_module.TokenTracker()
    tracker.calls = calls
    value["tracker"] = tracker
    return value


def campaign_fingerprint(
    chapters: dict[str, str], translation_units: dict[str, str], provider: str, model: str
) -> str:
    """计算整场实验的指纹：章节内容 / 翻译单元 / 提供商 / 模型任一变化都会失效。"""
    contract = {
        "chapters": {title: sha256_text(text) for title, text in chapters.items()},
        "translation_units": {
            title: sha256_text(text) for title, text in translation_units.items()
        },
        "provider": provider,
        "model": model,
    }
    return sha256_text(json.dumps(contract, ensure_ascii=False, sort_keys=True))


def load_checkpoint(path: Path, fingerprint: str) -> Any | None:
    """加载与当前指纹匹配的检查点；不匹配直接报错，禁止跨配置续跑。"""
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("campaign_fingerprint") != fingerprint:
        raise RuntimeError(f"检查点与本次实验配置不匹配：{path}")
    return payload["value"]


def main() -> int:
    """官方全量验收战役入口。"""
    parser = argparse.ArgumentParser(description="实验 10-2 官方全量验收战役")
    parser.add_argument(
        "--source", action="append",
        help="待翻译的 Markdown 章节文件；可重复传入（默认取 sample_book 前两章）",
    )
    parser.add_argument("--model", help="覆盖使用的模型（等价于在根目录 .env 设置 LLM_MODEL）")
    parser.add_argument(
        "--max-unit-characters", type=int, default=20_000,
        help="翻译单元的目标大小上限，单位字符（默认：20000）",
    )
    parser.add_argument("--output-dir", help="验证产物目录（默认按时间戳生成）")
    args = parser.parse_args()

    # --model 的覆盖必须在 import agents 之前生效：
    # llm.client 与 agents 都会读取 LLM_MODEL 环境变量。
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    # 延迟导入：确保上面对模型环境的任何调整先于客户端创建生效
    import agents
    import consistency

    paths = [Path(item).resolve() for item in args.source] if args.source else list(DEFAULT_SOURCES)
    chapters, source_paths = load_source_book(paths)
    translation_units, chapter_units = split_translation_units(
        chapters, max_characters=args.max_unit_characters
    )
    stats = source_statistics(chapters)
    stats["translation_unit_count"] = len(translation_units)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = Path(args.output_dir).resolve() if args.output_dir else HERE / "validation" / f"real_{timestamp}"
    output.mkdir(parents=True, exist_ok=True)
    # 指纹在运行前计算并写入全部检查点，用于断点续跑时校验配置未变
    fingerprint = campaign_fingerprint(
        chapters, translation_units, agents.ACTIVE_PROVIDER, agents.MODEL
    )

    started = time.perf_counter()
    orch_started = time.perf_counter()
    orchestration_checkpoint = output / "orchestration_checkpoint.json"
    saved_orchestration = load_checkpoint(orchestration_checkpoint, fingerprint)
    if saved_orchestration is None:
        orchestration = agents.run_orchestration(
            translation_units, str(output / "orchestration_parts"),
            source_lang="英文", target_lang="中文"
        )
        orchestration_elapsed = time.perf_counter() - orch_started
        write_json_atomic(orchestration_checkpoint, {
            "campaign_fingerprint": fingerprint,
            "value": {
                "result": serialize_arm(orchestration),
                "elapsed_seconds": orchestration_elapsed,
            },
        })
    else:
        orchestration = restore_arm(saved_orchestration["result"], agents)
        orchestration_elapsed = saved_orchestration["elapsed_seconds"]
    single_started = time.perf_counter()
    single_checkpoint = output / "single_agent_checkpoint.json"
    saved_single = load_checkpoint(single_checkpoint, fingerprint)
    if saved_single is None:
        single = agents.run_single_agent(
            translation_units, str(output / "single_agent_parts"),
            source_lang="英文", target_lang="中文"
        )
        single_elapsed = time.perf_counter() - single_started
        write_json_atomic(single_checkpoint, {
            "campaign_fingerprint": fingerprint,
            "value": {
                "result": serialize_arm(single),
                "elapsed_seconds": single_elapsed,
            },
        })
    else:
        single = restore_arm(saved_single["result"], agents)
        single_elapsed = saved_single["elapsed_seconds"]

    orchestration_complete = reassemble_translations(orchestration["translations"], chapter_units)
    single_complete = reassemble_translations(single["translations"], chapter_units)
    for mode, complete in (
        ("orchestration", orchestration_complete), ("single_agent", single_complete)
    ):
        destination = output / mode
        destination.mkdir(parents=True, exist_ok=True)
        for index, (title, text) in enumerate(complete.items(), start=1):
            (destination / f"chapter{index}_zh.md").write_text(text, encoding="utf-8")

    fidelity = {"orchestration": {}, "single_agent": {}}
    for title, source in chapters.items():
        fidelity["orchestration"][title] = markdown_fidelity(source, orchestration_complete[title])
        fidelity["single_agent"][title] = markdown_fidelity(source, single_complete[title])

    judge_client, judge_model, judge_provider = make_judge()
    judge_checkpoint = output / "judge_checkpoint.json"
    judge_receipt_dir = output / "judge_receipts"
    judge_receipt_dir.mkdir(parents=True, exist_ok=True)
    judge_rows = load_checkpoint(judge_checkpoint, fingerprint) or []
    expected_titles = list(translation_units)
    if [row.get("chapter") for row in judge_rows] != expected_titles[:len(judge_rows)]:
        raise RuntimeError("judge checkpoint order does not match translation units")
    for index, (title, source) in enumerate(translation_units.items()):
        if index < len(judge_rows):
            continue
        alias_to_mode = (
            {"X": "orchestration", "Y": "single_agent"}
            if index % 2 == 0 else {"X": "single_agent", "Y": "orchestration"}
        )
        translations = {
            "orchestration": orchestration["translations"][title],
            "single_agent": single["translations"][title],
        }
        result, usage = judge_chapter(
            judge_client, judge_model, source,
            translations[alias_to_mode["X"]], translations[alias_to_mode["Y"]],
            receipt_path=judge_receipt_dir / f"unit-{index + 1:02d}.json",
        )
        receipt = judge_receipt_dir / f"unit-{index + 1:02d}.json"
        judge_rows.append({
            "chapter": title,
            "alias_to_mode": alias_to_mode,
            "result": result,
            "usage": usage,
            "receipt": str(receipt.relative_to(output)),
            "receipt_sha256": sha256(receipt),
        })
        write_json_atomic(judge_checkpoint, {
            "campaign_fingerprint": fingerprint,
            "value": judge_rows,
        })

    orch_consistency = consistency.analyze(orchestration_complete)
    single_consistency = consistency.analyze(single_complete)
    orch_adherence = consistency.check_adherence(orchestration_complete)
    single_adherence = consistency.check_adherence(single_complete)
    all_agent_types = set(orchestration["tracker"].by_agent())
    translation_calls = orchestration["tracker"].calls + single["tracker"].calls
    # 全部翻译调用必须使用同一 (提供商, 模型) 组合，保证对比公平
    translation_fingerprints = {
        (call.get("provider"), call.get("model"))
        for call in translation_calls
    }
    translation_provider, translation_model = (
        next(iter(translation_fingerprints))
        if len(translation_fingerprints) == 1 else (None, None)
    )

    current_source_paths = [HERE / "run_official_experiment.py", HERE / "agents.py", HERE / "consistency.py"]
    checkpoint_paths = [orchestration_checkpoint, single_checkpoint, judge_checkpoint]
    translation_output_paths = [
        output / mode / f"chapter{index}_zh.md"
        for mode in ("orchestration", "single_agent")
        for index in range(1, len(chapters) + 1)
    ]
    prior_failure = output / "prior_judge_failure.json"

    def repo_hash_map(files: list[Path]) -> dict[str, str]:
        return {
            str(path.resolve().relative_to(REPO)): sha256(path)
            for path in files if path.is_file()
        }

    provenance = {
        "campaign_fingerprint": fingerprint,
        "current_acceptance_sources_sha256": repo_hash_map(current_source_paths),
        "arm_and_judge_checkpoints_sha256": repo_hash_map(checkpoint_paths),
        "reassembled_translation_outputs_sha256": repo_hash_map(translation_output_paths),
        "raw_judge_receipts_sha256": {
            str((output / row["receipt"]).resolve().relative_to(REPO)): row["receipt_sha256"]
            for row in judge_rows
        },
        "negative_provenance_sha256": repo_hash_map([prior_failure]),
        "resume_note": (
            "长任务从与指纹绑定的运行方式检查点与评审检查点续跑。"
            "当前验收源码哈希绑定最终的校验器/证据构建器；不可变的原始评审回执"
            "保留了每一次 schema 失败与修复调用。"
        ),
    }
    declared_provenance_hashes = {
        key: digest
        for field in (
            "current_acceptance_sources_sha256",
            "arm_and_judge_checkpoints_sha256",
            "reassembled_translation_outputs_sha256",
            "raw_judge_receipts_sha256",
            "negative_provenance_sha256",
        )
        for key, digest in provenance[field].items()
    }
    receipt_payloads = [
        json.loads((output / row["receipt"]).read_text(encoding="utf-8"))
        for row in judge_rows
    ]
    judge_attempt_count = sum(len(item.get("attempts", [])) for item in receipt_payloads)
    rejected_judge_attempt_count = sum(
        not attempt.get("validation", {}).get("valid", False)
        for item in receipt_payloads for attempt in item.get("attempts", [])
    )
    gates = {
        "real_illustrated_code_heavy_technical_book": (
            stats["chapter_count"] >= 2 and stats["bytes"] >= 200_000
            and stats["image_references"] >= 10 and stats["fenced_code_blocks"] >= 5
        ),
        "four_agent_roles_executed": {"Glossary", "Translation", "Proofreading", "Manager"}.issubset(all_agent_types),
        "both_modes_translated_every_chapter": all(
            orchestration_complete.get(title, "").strip()
            and single_complete.get(title, "").strip()
            for title in chapters
        ),
        "real_usage_recorded_for_every_call": all(
            call.get("prompt_tokens", 0) > 0 and call.get("provider") and call.get("model")
            for call in translation_calls
        ),
        "uniform_translation_api_fingerprint": (
            len(translation_fingerprints) == 1
            and all((translation_provider, translation_model))
        ),
        "manager_context_excludes_translation_bodies": all(
            text not in json.dumps(orchestration["manager_context_final"], ensure_ascii=False)
            for text in orchestration["translations"].values()
        ),
        "quality_compared_for_every_translation_unit": len(judge_rows) == len(translation_units),
        "raw_judge_receipts_hashed": len(judge_rows) == len(translation_units) and all(
            (output / row.get("receipt", "missing")).is_file()
            and sha256(output / row["receipt"]) == row.get("receipt_sha256")
            for row in judge_rows
        ),
        "raw_judge_response_ids_and_usage_recorded": all(
            item.get("attempts") and all(
                attempt.get("response", {}).get("id")
                and attempt.get("response", {}).get("usage", {}).get("prompt_tokens", 0) > 0
                and attempt.get("response", {}).get("usage", {}).get("completion_tokens", 0) > 0
                for attempt in item["attempts"]
            )
            for item in receipt_payloads
        ),
        "checkpoint_fingerprints_match": all(
            json.loads(path.read_text(encoding="utf-8")).get("campaign_fingerprint") == fingerprint
            for path in checkpoint_paths
        ),
        "all_declared_provenance_hashes_match": all(
            (REPO / relative).is_file() and sha256(REPO / relative) == digest
            for relative, digest in declared_provenance_hashes.items()
        ),
        "efficiency_and_resources_compared": (
            orchestration_elapsed > 0 and single_elapsed > 0
            and orchestration["tracker"].total_tokens() > 0 and single["tracker"].total_tokens() > 0
        ),
    }
    artifact = {
        "schema_version": 1,
        "experiment": "10-3",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_book": {
            "identity": f"{len(chapters)} 个 Markdown 输入章节（默认 sample_book，可 --source 覆盖）",
            "paths": source_paths,
            "sha256": {title: sha256(paths[index]) for index, title in enumerate(chapters)},
            "statistics": stats,
            "max_translation_unit_characters_requested": args.max_unit_characters,
            "translation_unit_sha256": {
                title: sha256_text(text) for title, text in translation_units.items()
            },
            "chapter_translation_units": chapter_units,
        },
        "translation_api": {
            "provider": translation_provider,
            "model": translation_model,
        },
        "quality_judge_api": {
            "provider": judge_provider,
            "model": judge_model,
            "raw_receipted_calls": judge_attempt_count,
            "known_pre_receipt_failures": 1 if prior_failure.is_file() else 0,
            "known_total_calls": judge_attempt_count + (1 if prior_failure.is_file() else 0),
            "rejected_receipted_schema_attempts": rejected_judge_attempt_count,
            "lossless_local_schema_normalizations": sum(
                bool(row["result"].get("schema_repairs")) for row in judge_rows
            ),
            "schema_formatting_repair_api_calls": sum(
                attempt.get("request_kind") == "schema_repair"
                for item in receipt_payloads for attempt in item.get("attempts", [])
            ),
            "prompt_tokens": sum(row["usage"]["prompt_tokens"] for row in judge_rows),
            "completion_tokens": sum(row["usage"]["completion_tokens"] for row in judge_rows),
            "latency_milliseconds": sum(
                row["usage"]["latency_milliseconds"] for row in judge_rows
            ),
        },
        "modes": {
            "orchestration": {
                "elapsed_seconds": orchestration_elapsed,
                "manager_context_peak": orchestration["manager_context_peak"],
                "tracker": tracker_receipt(orchestration["tracker"]),
                "terminology_consistency": orch_consistency,
                "mandated_terminology_adherence": orch_adherence,
            },
            "single_agent": {
                "elapsed_seconds": single_elapsed,
                "main_context_peak": single["main_context_peak"],
                "tracker": tracker_receipt(single["tracker"]),
                "terminology_consistency": single_consistency,
                "mandated_terminology_adherence": single_adherence,
            },
        },
        "markdown_fidelity": fidelity,
        "blinded_quality_judges": judge_rows,
        "quality_aggregate": aggregate_judges(judge_rows),
        "comparison": {
            "context_peak": {
                "orchestration_manager": orchestration["manager_context_peak"],
                "single_agent": single["main_context_peak"],
            },
            "wall_clock_seconds": {
                "orchestration": orchestration_elapsed,
                "single_agent": single_elapsed,
            },
            "total_tokens": {
                "orchestration": orchestration["tracker"].total_tokens(),
                "single_agent": single["tracker"].total_tokens(),
            },
        },
        "provenance": provenance,
        "acceptance_gates": gates,
        "experiment_execution_complete": all(gates.values()),
        "total_campaign_active_seconds": (
            orchestration_elapsed + single_elapsed
            + sum(row["usage"]["latency_milliseconds"] for row in judge_rows) / 1000
        ),
        "finalization_session_seconds": time.perf_counter() - started,
        "interpretation_rule": (
            "“完成”指全量对比通过真实 API 运行且全部必需指标齐备；"
            "并不要求管理者模式在每一项指标上都胜出。"
        ),
    }
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest = HERE / "validation" / "latest.json"
    latest.write_text(json.dumps({
        "experiment": "10-3",
        "status": "complete" if artifact["experiment_execution_complete"] else "incomplete",
        "evidence": str(evidence.relative_to(HERE)),
        "evidence_sha256": sha256(evidence),
        "acceptance_gates": gates,
        "comparison": artifact["comparison"],
        "quality_aggregate": artifact["quality_aggregate"],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "evidence": str(evidence),
        "complete": artifact["experiment_execution_complete"],
        "source_statistics": stats,
        "comparison": artifact["comparison"],
        "quality": artifact["quality_aggregate"],
    }, ensure_ascii=False, indent=2))
    return 0 if artifact["experiment_execution_complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
