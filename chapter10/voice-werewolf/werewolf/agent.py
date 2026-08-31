# -*- coding: utf-8 -*-
"""玩家 Agent：每个玩家 = 一个独立的 LLM Agent，拥有**严格隔离的私有上下文**。

信息隔离的实现要点：
- 每个 PlayerAgent 只维护自己的 `memory`（一串它「观察到 / 被告知」的事件）。
- 法官（game.py）决定把哪条信息推给哪个 Agent 的 memory——狼人才会收到「队友
  身份」，预言家才会收到「查验结果」，公开发言才会推给所有人。
- Agent 每次思考（发言 / 投票 / 用技能）时，只能看到自己 memory 里的内容，
  因此不可能「偷看」到本不该看到的信息。这就是信息权限控制的落点。

离线（--offline / --mock）策略：当想零成本可复现地跑完整一局时，Agent 用一套
**规则驱动**的决策代替 LLM。关键在于：离线策略同样**只读自己的 memory**（不碰
其他 Agent 的私有上下文），因此信息权限控制这一教学要点在离线模式下依然成立、
依然可被审计校验。
"""

import json
import os
import re
import sys
from typing import List, Optional

# 添加项目根目录到路径（用于导入统一的 llm.client 模块）
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from .roles import Role, ROLE_STRATEGY, faction_of

try:
    from llm.client import get_llm_client, get_llm_config
except ImportError:
    get_llm_client = None
    get_llm_config = None


# 全局唯一的 LLM 客户端（懒加载，进程内单例）。模型名从项目根目录 .env 配置读取。
_client = None
_MODEL = None


def _safe_create(client, **kwargs):
    """调用 Chat Completions；对推理型模型（如 gpt-5.x 系列）的参数限制做自动降级重试：
    - 不支持 max_tokens 时改用 max_completion_tokens；
    - 不支持非默认 temperature 时移除该参数（回退到模型默认 1）。
    这样同一份代码既能跑传统对话模型（接受 temperature=0.8），也能跑推理模型。"""
    for _ in range(3):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            msg = str(e)
            # 某些推理型模型只认 max_completion_tokens，自动替换参数名后重试
            if "max_completion_tokens" in msg and "max_tokens" in kwargs:
                kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
                continue
            # 某些推理型模型不支持自定义 temperature，移除后回退到模型默认值
            if "temperature" in msg and "temperature" in kwargs:
                kwargs.pop("temperature", None)
                continue
            raise
    return client.chat.completions.create(**kwargs)


def get_client():
    """返回全局共享的 LLM 客户端（懒加载，进程内单例）。

    客户端配置统一来自项目根目录的 .env 文件（API_KEY / LLM_PROVIDER /
    LLM_MODEL / BASE_URL），本模块不自行管理任何密钥或端点。
    仅在线模式（真实调用 LLM）才会用到；离线模式不构造客户端。
    """
    global _client, _MODEL
    if _client is None:
        if get_llm_client is None:
            raise RuntimeError(
                "无法导入统一 LLM 客户端 llm.client。请从项目根目录运行，"
                "或改用离线模式：python demo.py --offline"
            )
        # 统一客户端自动读取 .env 配置；附加超时与重试参数（项目特定）
        _client = get_llm_client()
        _client.timeout = float(os.getenv("WEREWOLF_LLM_TIMEOUT", "45"))
        _client.max_retries = int(os.getenv("WEREWOLF_LLM_RETRIES", "1"))
        _MODEL = _client.model_name
    return _client


def reset_client():
    """重置全局客户端（用于 --model 等运行时切换模型后强制重建）。"""
    global _client, _MODEL
    _client = None
    _MODEL = None


def current_model() -> str:
    """返回当前生效的模型名（未初始化时从 .env 配置解析）。"""
    if _MODEL is not None:
        return _MODEL
    if get_llm_config is not None:
        config = get_llm_config()
        return config.get("model") or "（未配置）"
    return "（未配置）"


class PlayerAgent:
    """一个玩家 Agent，封装其身份、私有上下文与决策（LLM 或离线规则）。"""

    def __init__(self, name: str, role: Role, offline: bool = False, rng=None):
        self.name = name          # 玩家名，如 "P3"
        self.role = role          # 真实身份（只有本人和法官知道）
        self.faction = faction_of(role)
        self.alive = True
        self.offline = offline    # True 时用规则策略代替 LLM（零成本、可复现）
        # 离线策略的私有随机源（按玩家名种子化，保证可复现且各玩家独立）
        import random as _random
        self._rng = rng or _random.Random(hash(name) & 0xFFFF)
        # 私有上下文：这个 Agent「看得到」的全部信息。别的 Agent 无法访问。
        self.memory: List[str] = []

    # ---- 上下文注入：只有法官会调用，用来把信息投递进这个 Agent 的私有上下文 ----
    def observe(self, event: str):
        """把一条信息写入本 Agent 的私有上下文。"""
        self.memory.append(event)

    # ---- system prompt：角色设定 + 策略。狼人的队友身份不写在这里，而是由法官
    #      在游戏开始时通过 observe() 投递，以便审计能记录「谁看到了队友身份」。 ----
    def _system_prompt(self, players: List[str]) -> str:
        return (
            f"你正在玩一局狼人杀。你是玩家 {self.name}。\n"
            f"你的真实身份是【{self.role.value}】，属于【{self.faction.value}】。\n"
            f"本局玩家共 {len(players)} 人：{'、'.join(players)}。\n\n"
            f"{ROLE_STRATEGY[self.role]}\n\n"
            "重要：只能依据你已知的信息推理，不要臆造你无从得知的身份。发言要像真人，"
            "简洁自然，有理有据。"
        )

    def _context_block(self) -> str:
        """把私有上下文拼成给 LLM 的一段文字。"""
        if not self.memory:
            return "（暂无信息）"
        return "\n".join(f"- {m}" for m in self.memory)

    def _chat(self, instruction: str, players: List[str], max_tokens: int,
              json_mode: bool = False) -> str:
        """组装 system + user 消息并调用 LLM；user 消息里只拼接本 Agent 自己的
        私有上下文（`_context_block`），绝不包含其他玩家的私密信息。"""
        messages = [
            {"role": "system", "content": self._system_prompt(players)},
            {"role": "user", "content":
                f"【你目前掌握的信息（仅你可见）】\n{self._context_block()}\n\n"
                f"【当前任务】\n{instruction}"},
        ]
        # 给推理型模型留足输出预算：其内部推理 token 也计入 max_tokens，
        # 预算过小会导致 content 被截断为空。设一个下限兜底。
        client = get_client()
        kwargs = dict(model=client.model_name, messages=messages, temperature=0.8,
                      max_tokens=max(max_tokens, 512))
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = _safe_create(client, **kwargs)
        content = (resp.choices[0].message.content or "").strip()
        if not content:
            # 部分推理模型会把小额动作预算全部花在隐藏推理上，返回不可见的
            # 发言/JSON。以有界的更大预算重试一次；若第二次仍为空，作为硬失败
            # 抛出，而不是变成沉默发言或随机动作。
            retry_kwargs = dict(kwargs)
            budget_key = (
                "max_completion_tokens"
                if "max_completion_tokens" in retry_kwargs
                else "max_tokens"
            )
            retry_kwargs[budget_key] = max(int(retry_kwargs.get(budget_key, 0)) * 4, 2048)
            resp = _safe_create(client, **retry_kwargs)
            content = (resp.choices[0].message.content or "").strip()
        if not content:
            raise RuntimeError("LLM 在有界重试后仍返回空内容")
        return content

    # ---------- 三种对外能力：发言 / 决策（选目标）/ 投票 ----------

    def speak(self, players: List[str]) -> str:
        """白天公开发言。返回一段发言文本（公开信息）。"""
        if self.offline:
            return self._offline_speak(candidates=[p for p in players if p != self.name])
        instruction = (
            "现在轮到你在白天公开发言。请结合你掌握的信息，发表一段简短的发言"
            "（2~4 句话，60 字以内）。符合你的身份与策略。直接输出发言内容，不要加引号。"
        )
        return self._chat(instruction, players, max_tokens=180)

    def choose_target(self, prompt: str, candidates: List[str],
                      players: List[str], allow_none: bool = False) -> Optional[str]:
        """让 Agent 从候选人中选一个目标（夜间刀人 / 查验 / 用毒 / 救人判断等）。

        用 JSON 模式返回，鲁棒地解析出目标玩家名。
        """
        if self.offline:
            return self._offline_choose_target(candidates, allow_none)
        opt = "，也可以选择放弃（target 填 \"none\"）" if allow_none else ""
        instruction = (
            f"{prompt}\n候选玩家：{'、'.join(candidates)}{opt}。\n"
            "请只返回 JSON：{\"target\": \"玩家名或none\", \"reason\": \"一句话理由\"}"
        )
        raw = self._chat(instruction, players, max_tokens=120, json_mode=True)
        self.last_decision_reason = self._parse_reason(raw)
        target = self._parse_target(raw, candidates, allow_none)
        return target

    def vote(self, candidates: List[str], players: List[str]) -> Optional[str]:
        """投票放逐。返回票投给谁（或弃票 none）。"""
        if self.offline:
            return self._offline_vote(candidates)
        instruction = (
            "现在是白天投票放逐环节。请根据全场发言与你的推理，投出你认为最可能是"
            "狼人的玩家。好人阵营必须按证据强度决策：没有对跳且已报告自洽查验结果的"
            "预言家声明是当前最强公开证据；除非有具体矛盾或另一名预言家对跳，不得投该"
            "声明者。若其报告某玩家是狼人，应优先投被查杀者；被查杀者仅仅否认并不构成"
            "矛盾或对跳。投票理由必须引用具体发言、查验或既有票型，不得随机猜测。\n"
            "候选玩家：" + "、".join(candidates) + "。\n"
            "请只返回 JSON：{\"target\": \"玩家名\", \"reason\": \"一句话理由\"}"
        )
        raw = self._chat(instruction, players, max_tokens=120, json_mode=True)
        self.last_decision_reason = self._parse_reason(raw)
        return self._parse_target(raw, candidates, allow_none=True)

    # ---------- 离线（规则）策略：只读自己的 memory，绝不访问他人上下文 ----------
    def _known_teammates(self) -> set:
        """狼人从自己的私有上下文里解析出队友名单（好人解析不到，返回空）。"""
        mates = set()
        for m in self.memory:
            hit = re.search(r"狼人阵营的玩家是：([^（(]+)", m)
            if hit:
                mates |= set(re.findall(r"P\d+", hit.group(1)))
        return mates

    def _known_wolves(self) -> set:
        """从自己的私有上下文里收集『已知是狼人』的玩家：预言家的查验结果 + 狼人的队友。

        好人平民无从得知任何人身份 → 返回空集合，只能随机投票。这正是信息不对称。
        """
        known = set(self._known_teammates())
        for m in self.memory:
            hit = re.search(r"你查验了\s*(P\d+)，结果为【狼人】", m)
            if hit:
                known.add(hit.group(1))
        return known

    def _offline_vote(self, candidates: List[str]) -> Optional[str]:
        """离线投票：优先投自己『确知的狼人』（预言家验人 / 狼人不投队友），否则随机。"""
        if not candidates:
            return None
        if self.role == Role.WEREWOLF:
            # 狼人：投一个非队友的好人，尽量隐藏自己
            mates = self._known_teammates()
            targets = [c for c in candidates if c not in mates] or candidates
            return self._rng.choice(targets)
        # 好人：预言家有验人结果就投确认的狼；其余平民只能随机（信息不对称的代价）
        wolves = [c for c in candidates if c in self._known_wolves()]
        if wolves:
            return self._rng.choice(wolves)
        return self._rng.choice(candidates)

    def _offline_choose_target(self, candidates: List[str],
                               allow_none: bool) -> Optional[str]:
        """离线夜间选目标：狼人/预言家等必选场景优先选『已知狼人之外』的目标；
        女巫解药/毒药等可放弃场景按概率决定。"""
        if not candidates:
            return None
        if allow_none:
            # 女巫用药：约一半概率行动（救/毒），使对局有变化又能收敛
            if self._rng.random() < 0.5:
                return None
            return self._rng.choice(candidates)
        if self.role == Role.SEER:
            # 预言家：优先查验尚未确认身份的玩家（避免重复查验已知狼人）
            unknown = [c for c in candidates if c not in self._known_wolves()]
            return self._rng.choice(unknown or candidates)
        if self.role == Role.WEREWOLF:
            mates = self._known_teammates()
            targets = [c for c in candidates if c not in mates] or candidates
            return self._rng.choice(targets)
        return self._rng.choice(candidates)

    def _offline_speak(self, candidates: List[str]) -> str:
        """离线发言：按角色生成一句符合身份、且不泄露私密信息的模板发言。"""
        wolves = [c for c in candidates if c in self._known_wolves()]
        suspect = self._rng.choice(candidates) if candidates else "大家"
        if self.role == Role.SEER and wolves:
            return f"我是预言家，昨晚查验到 {wolves[0]} 是狼人，请大家把票投给他。"
        if self.role == Role.WEREWOLF:
            return f"我是好人，从发言看 {suspect} 有点可疑，建议重点关注他。"
        if self.role == Role.WITCH:
            return f"我暂时观望，觉得 {suspect} 的发言站不住脚，先留意一下。"
        if self.role == Role.SEER:
            return "我还没有决定性的信息，先听大家发言，谨慎投票。"
        return f"我是村民，没有夜间信息，只能靠推理，感觉 {suspect} 稍微可疑。"

    # ---------- 解析工具 ----------
    @staticmethod
    def _parse_reason(raw: str) -> Optional[str]:
        """从模型返回的 JSON 里提取决策理由；解析失败返回 None。"""
        try:
            reason = json.loads(raw).get("reason")
        except Exception:
            return None
        return reason.strip() if isinstance(reason, str) and reason.strip() else None

    @staticmethod
    def _parse_target(raw: str, candidates: List[str], allow_none: bool) -> Optional[str]:
        """从模型返回的文本中鲁棒地解析出目标玩家名。"""
        target = None
        try:
            data = json.loads(raw)
            target = str(data.get("target", "")).strip()
        except Exception:
            # 兜底：直接从文本里正则找候选玩家名
            target = raw
        if allow_none and target.lower() in ("none", "", "弃票", "放弃"):
            return None
        # 归一化：精确匹配优先
        if target in candidates:
            return target
        # 其次：从原始串里搜 Pn 精确 token。必须先于子串匹配——
        # 否则 10 人以上的局里 "P10（他最可疑）" 会先命中 "P1"。
        m = re.search(r"P\d+", target or "")
        if m and m.group(0) in candidates:
            return m.group(0)
        # 最后兜底：子串匹配，最长的候选名优先（避免 P1 抢先命中 P10）
        for c in sorted(candidates, key=len, reverse=True):
            if c in (target or ""):
                return c
        # 实在解析不出：好人默认弃票，狼人/必须选的场景由调用方兜底
        return None if allow_none else (candidates[0] if candidates else None)
