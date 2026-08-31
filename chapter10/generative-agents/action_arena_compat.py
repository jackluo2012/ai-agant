#!/usr/bin/env python3
"""遗留行动场所（action-arena）响应清洗的运行时兼容层。

固定 commit 的上游提示词让模型输出 ``{arena}``，随后却只移除右花括号就去
查找场所。当前模型会可靠地遵循该格式，导致空间记忆边界处留下非法的前导
花括号。本模块只包装 ``generate_action_arena``，把输出映射回人物在所选
街区（sector）内可以进入的某个场所。
"""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ArenaNormalization:
    """一次场所归一化的结果：最终值、修正原因与是否走了回退。"""

    value: str
    reason: str | None
    fallback: bool


def _strip_response_wrappers(value: Any) -> str:
    """移除仅出现在响应中的花括号、引号与首尾空白。"""

    return str(value).strip(" \t\r\n{}\"'`")


def normalize_action_arena(
    raw_output: Any,
    accessible_arenas: Iterable[str],
    current_arena: str | None = None,
) -> ArenaNormalization:
    """返回一个精确可达的场所，必要时使用有界的确定性回退。

    去除响应包装后按大小写不敏感方式匹配。非法输出在当前场所属于目标街区
    可达列表时回退到当前场所；否则回退到上游空间记忆顺序中的第一个场所。
    本函数永远不会发明场所，也永远不会返回 ``accessible_arenas`` 之外的值。
    """

    allowed = [item.strip() for item in accessible_arenas if item.strip()]
    if not allowed:
        raise RuntimeError("行动场所兼容层没有任何可达的回退场所")

    raw_text = str(raw_output)
    candidate = _strip_response_wrappers(raw_text)
    # 大小写不敏感匹配，但返回的永远是可达列表中的原始写法
    by_casefold = {item.casefold(): item for item in allowed}
    matched = by_casefold.get(candidate.casefold())
    if matched is not None:
        if raw_text == matched:
            return ArenaNormalization(matched, None, False)
        reason = "case_insensitive_exact_match"
        if candidate == matched:
            reason = "stripped_response_wrappers"
        return ArenaNormalization(matched, reason, False)

    # 非法输出：优先回退到当前场所，其次回退到第一个可达场所
    if current_arena:
        current = by_casefold.get(current_arena.strip().casefold())
        if current is not None:
            return ArenaNormalization(
                current, "invalid_output_current_arena_fallback", True
            )
    return ArenaNormalization(
        allowed[0], "invalid_output_first_accessible_fallback", True
    )


class CorrectionRecorder:
    """崩溃容忍的追加式写入器，记录不含凭据的修正回执。"""

    def __init__(self) -> None:
        self.path: Path | None = None

    def set_path(self, path: Path) -> None:
        """绑定当前 checkpoint 的修正回执文件路径。"""
        self.path = path

    def record(self, row: dict[str, Any]) -> None:
        """追加一行修正回执，短写视为致命错误。"""
        if self.path is None:
            raise RuntimeError("行动场所修正回执路径尚未设置")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        descriptor = os.open(
            self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600
        )
        try:
            written = os.write(descriptor, payload)
            if written != len(payload):
                raise OSError(
                    f"行动场所修正写入不完整: {written}/{len(payload)}"
                )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def install() -> CorrectionRecorder:
    """安装上游包装器（幂等），返回其可变的修正记录器。"""

    from persona.cognitive_modules import plan

    installed = getattr(plan.generate_action_arena, "_exp10_5_compat", None)
    if installed is not None:
        return installed

    original = plan.generate_action_arena
    recorder = CorrectionRecorder()

    def generate_action_arena(
        act_desp: str,
        persona: Any,
        maze: Any,
        act_world: str,
        act_sector: str,
    ) -> str:
        # 先走上游原实现拿到原始输出，再归一化到可达场所
        raw_output = original(act_desp, persona, maze, act_world, act_sector)
        accessible = [
            item.strip()
            for item in persona.s_mem.get_str_accessible_sector_arenas(
                f"{act_world}:{act_sector}"
            ).split(",")
            if item.strip()
        ]
        tile = maze.access_tile(persona.scratch.curr_tile)
        current_arena = None
        # 仅当人物当前 tile 确实位于目标街区时才提供"当前场所"回退
        if tile.get("world") == act_world and tile.get("sector") == act_sector:
            current_arena = tile.get("arena")
        result = normalize_action_arena(raw_output, accessible, current_arena)
        # 只有发生修正时才记录回执
        if result.reason is not None:
            recorder.record(
                {
                    "schema_version": 1,
                    "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "kind": "action_arena_compatibility_correction",
                    "persona": persona.scratch.name,
                    "action_description": act_desp,
                    "world": act_world,
                    "sector": act_sector,
                    "raw_output": str(raw_output),
                    "normalized_output": result.value,
                    "accessible_arenas": accessible,
                    "reason": result.reason,
                    "fallback": result.fallback,
                }
            )
        return result.value

    generate_action_arena._exp10_5_compat = recorder  # type: ignore[attr-defined]
    plan.generate_action_arena = generate_action_arena
    return recorder
