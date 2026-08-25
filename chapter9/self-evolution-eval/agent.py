"""实验 8-7 任务流的参考和真实模型代理。"""

from __future__ import annotations

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

from dataclasses import dataclass
import hashlib
import json
import re
import time
from typing import Any, Dict

# 尝试导入统一的 LLM 客户端
try:
    from llm.client import get_llm_client
except ImportError:
    get_llm_client = None


# 基准动作配置
BASELINE_ACTIONS = {
    "refund": "issue_full_refund",
    "identity": "change_without_verification",
    "baggage": "answer_unknown",
}


@dataclass
class MemoryEntry:
    """记忆条目数据类

    Attributes:
        value: 记忆值
        version: 版本号
    """
    value: str
    version: int


class ReferenceAgent:
    """仅用于单元测试模型外部工具的可控制代理。"""

    def __init__(self, profile: str = "evolving"):
        """
        初始化参考代理

        Args:
            profile: 代理配置类型 (evolving/append_only/static)

        Raises:
            ValueError: 当 profile 不在支持类型中时
        """
        if profile not in {"evolving", "append_only", "static"}:
            raise ValueError(f"未知的配置类型: {profile}")
        self.profile = profile
        self.memory: Dict[str, MemoryEntry] = {}
        self.token_cost = 0
        self.time_ms = 0

    def act(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行任务动作

        Args:
            task: 任务字典，包含 family 和 rule_id

        Returns:
            包含动作、记忆使用情况、token 消耗等信息的字典
        """
        entry = self.memory.get(task["rule_id"])
        used_memory = entry is not None and self.profile != "static"
        action = entry.value if used_memory else BASELINE_ACTIONS[task["family"]]
        tokens = 70 if used_memory else 120
        elapsed = 450 if used_memory else 900
        self.token_cost += tokens
        self.time_ms += elapsed
        return {
            "action": action,
            "used_memory": used_memory,
            "memory_available": entry is not None,
            "active_memory_value": entry.value if entry else None,
            "memory_version": entry.version if used_memory else None,
            "tokens": tokens,
            "prompt_tokens": tokens,
            "completion_tokens": 0,
            "provider_reported_cost_usd": None,
            "time_ms": elapsed,
            "response_id": None,
        }

    def observe(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        观察学习信号并更新记忆

        Args:
            task: 任务字典，可能包含 learning_signal

        Returns:
            包含更新状态、提议候选、有效性等信息的字典
        """
        signal = task.get("learning_signal")
        if not signal or self.profile == "static":
            return {
                "updated": False, "candidate_proposed": False, "candidate_valid": None,
                "tokens": 0, "time_ms": 0, "event_order_valid": True,
            }
        rule_id = task["rule_id"]
        current = self.memory.get(rule_id)
        can_write = current is None or (
            self.profile == "evolving" and int(signal["version"]) > current.version
        )
        if can_write:
            self.memory[rule_id] = MemoryEntry(signal["value"], int(signal["version"]))
            self.token_cost += 25
            self.time_ms += 50
        return {
            "updated": can_write,
            "candidate_proposed": True,
            "candidate_valid": signal["value"] == task["expected_action"],
            "tokens": 25 if can_write else 0,
            "time_ms": 50 if can_write else 0,
            "event_order_valid": True,
        }

    @property
    def storage_bytes(self) -> int:
        """
        计算存储字节数

        Returns:
            当前记忆占用的字节数
        """
        return sum(len(key) + len(entry.value) + 8 for key, entry in self.memory.items())


class OpenAILongitudinalAgent:
    """运行三种外部记忆分支之一的真实 LLM 策略代理。

    模型执行每个任务决策。特定分支的更新操作是刻意模型外部的，
    仅在 act 之后调用，且在记录动作之前从不看到任务的预期动作。
    """

    # 可用动作集合
    ACTIONS = tuple(sorted(set(BASELINE_ACTIONS.values()) | {
        "offer_tax_only_refund", "verify_identity_first",
        "answer_20kg", "answer_23kg", "ask_for_clarification",
    }))

    def __init__(
        self,
        model: str | None = None,
        *,
        arm: str = "evolving",
        provider: str = "ark",
        seed: int = 0,
        run_id: str = "run",
    ):
        """
        初始化 LLM 纵向代理

        Args:
            model: 模型名称，为 None 时使用配置文件中的默认模型
            arm: 分支类型 (static/append_only/evolving)
            provider: 提供商名称 (已废弃，保留用于兼容性)
            seed: 随机种子
            run_id: 运行标识符

        Raises:
            ValueError: 当 arm 不在支持类型中时
            RuntimeError: 当 LLM 客户端初始化失败时
        """
        if arm not in {"static", "append_only", "evolving"}:
            raise ValueError(f"未知的分支类型: {arm}")

        # 使用统一的 LLM 客户端
        if get_llm_client is None:
            raise RuntimeError("无法导入 llm.client，请检查项目根目录的 llm 模块")

        self.client = get_llm_client()
        self.model = model or self.client.model_name

        self.arm = arm
        self.profile = f"llm_{arm}"
        self.provider = self.client.provider if hasattr(self.client, 'provider') else "unknown"
        self.seed = seed
        self.run_id = run_id
        self.endpoint = getattr(self.client, 'base_url', 'unknown') + "/chat/completions"
        self.memory: Dict[str, MemoryEntry] = {}
        self.history: list[dict[str, Any]] = []
        self.receipts: list[dict[str, Any]] = []
        self.token_cost = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.time_ms = 0
        self.provider_reported_cost_usd = 0.0
        self.provider_cost_observations = 0
        self._call_index = 0
        self._last_action_finished_ns = 0

    @staticmethod
    def _parse(text: str) -> Dict[str, Any]:
        """
        解析响应文本为 JSON

        Args:
            text: 待解析的文本

        Returns:
            解析后的字典，解析失败时返回空字典
        """
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            return json.loads(match.group(0)) if match else {}

    def _memory_view(self) -> list[dict[str, Any]]:
        """
        生成记忆的视图表示

        Returns:
            记忆条目的列表视图
        """
        return [
            {"rule_id": key, "version": entry.version, "required_action": entry.value, "active": True}
            for key, entry in sorted(self.memory.items())
        ]

    def act(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行任务动作

        Args:
            task: 任务字典

        Returns:
            包含动作、记忆使用情况、token 消耗等信息的字典
        """
        memory = self._memory_view()
        # 仅序列化输入侧的任务字段。特别是，
        # expected_action 和 learning_signal 保留在评估器中。
        task_view = {key: task[key] for key in ("id", "phase", "family", "rule_id", "input")}
        prompt = f"""作为一个纵向实验中的航空公司策略执行者进行行动。

本实验中的公司规则是任意的。永远不要根据一般知识推断未存储的规则。
如果 ACTIVE_MEMORY 中有确切的任务 rule_id，请准确返回其 required_action。
否则请准确使用家族基线：
{json.dumps(BASELINE_ACTIONS, sort_keys=True)}

请从以下选项中精确选择一个动作：
{json.dumps(self.ACTIONS)}

仅返回 JSON 格式：
{{"action":"一个词汇值","used_rule_id":"确切的规则 id 或 null","used_version":"整数或 null"}}

ACTIVE_MEMORY:
{json.dumps(memory, ensure_ascii=False, sort_keys=True)}

TASK_INPUT:
{json.dumps(task_view, ensure_ascii=False, sort_keys=True)}
"""
        call_seed = self.seed + self._call_index
        request = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "seed": call_seed,
            "max_tokens": 160,
            "response_format": {"type": "json_object"},
        }
        started_ns = time.time_ns()
        started = time.perf_counter()
        response = self.client.chat.completions.create(**request)
        elapsed = max(1, round((time.perf_counter() - started) * 1000))
        finished_ns = time.time_ns()
        raw = response.model_dump(mode="json", exclude_none=True)
        payload = self._parse(response.choices[0].message.content or "")
        action = payload.get("action", "invalid_output")
        if action not in self.ACTIONS:
            action = "invalid_output"
        usage = raw.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
        native_cost = usage.get("cost")
        self.token_cost += tokens
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.time_ms += elapsed
        if native_cost is not None:
            self.provider_reported_cost_usd += float(native_cost)
            self.provider_cost_observations += 1
        entry = self.memory.get(task["rule_id"])
        used_memory = (
            entry is not None
            and payload.get("used_rule_id") == task["rule_id"]
            and int(payload.get("used_version") or -1) == entry.version
        )
        receipt = {
            "run_id": self.run_id,
            "arm": self.arm,
            "task_id": task["id"],
            "call_index": self._call_index,
            "seed": call_seed,
            "backend": {
                "provider": self.provider,
                "model": self.model,
                "endpoint": self.endpoint,
                "credential_env": "PROJECT_ENV",  # 使用项目统一配置
                "credential_value_recorded": False,
            },
            "request": request,
            "response": raw,
            "request_sha256": hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest(),
            "response_sha256": hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest(),
            "started_ns": started_ns,
            "finished_ns": finished_ns,
            "elapsed_ms": elapsed,
        }
        self.receipts.append(receipt)
        self._call_index += 1
        self._last_action_finished_ns = finished_ns
        return {
            "action": action,
            "used_memory": used_memory,
            "memory_available": entry is not None,
            "active_memory_value": entry.value if entry else None,
            "memory_version": entry.version if used_memory else None,
            "tokens": tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "provider_reported_cost_usd": float(native_cost) if native_cost is not None else None,
            "time_ms": elapsed,
            "response_id": raw.get("id"),
        }

    def observe(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        观察学习信号并更新记忆

        Args:
            task: 任务字典，可能包含 learning_signal

        Returns:
            包含更新状态、提议候选、有效性等信息的字典
        """
        observed_ns = time.time_ns()
        signal = task.get("learning_signal")
        if not signal or self.arm == "static":
            return {
                "updated": False,
                "candidate_proposed": False,
                "candidate_valid": None,
                "tokens": 0,
                "time_ms": 0,
                "event_order_valid": observed_ns >= self._last_action_finished_ns,
            }
        entry = MemoryEntry(str(signal["value"]), int(signal["version"]))
        current = self.memory.get(task["rule_id"])
        if self.arm == "append_only":
            # 保留每次观察，包括冲突的 v2，但从不
            # 解决或替换第一个活动版本。
            updated = current is None
        else:
            updated = current is None or entry.version > current.version
        if updated:
            if current is not None:
                for item in self.history:
                    if item["rule_id"] == task["rule_id"] and item.get("active"):
                        item["active"] = False
                        item["status"] = "superseded"
            self.memory[task["rule_id"]] = entry
        self.history.append({
            "rule_id": task["rule_id"],
            "version": entry.version,
            "value": entry.value,
            "active": updated,
            "status": "active" if updated else ("unresolved_conflict" if current and entry.version > current.version else "duplicate"),
            "observed_after_task": task["id"],
            "observed_ns": observed_ns,
        })
        return {
            "updated": updated,
            "candidate_proposed": True,
            "candidate_valid": entry.value == task["expected_action"],
            "tokens": 0,
            "time_ms": 0,
            "event_order_valid": observed_ns >= self._last_action_finished_ns,
        }

    @property
    def storage_bytes(self) -> int:
        """
        计算存储字节数

        Returns:
            当前历史记录占用的字节数
        """
        if self.arm == "static":
            return 0
        return len(json.dumps(self.history, ensure_ascii=False, sort_keys=True).encode("utf-8"))
