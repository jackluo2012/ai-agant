"""实验 10-3 的共享数据契约。

这些契约被刻意设计为可序列化：Computer/Phone Agent 的每一条消息交换都会写入
时序轨迹文件，因此一次运行可以证明"何时决定了什么"。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class FieldSpec:
    """单个表单字段的规格：名称、标签、类型、校验规则与选项。"""

    name: str
    label: str
    input_type: str = "text"
    required: bool = True
    selector: str = ""
    format_hint: str = ""
    pattern: str = ""
    options: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "FieldSpec":
        # 只接受数据类已声明的字段，过滤掉浏览器探测产生的多余键
        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in value.items() if k in allowed})

    def validate(self, value: Optional[str]) -> tuple[bool, str]:
        """
        校验一个候选值是否符合该字段的要求

        Args:
            value: 待校验的候选值（可为 None）

        Returns:
            (是否通过, 失败原因)；通过时原因为空字符串
        """
        val = (str(value) if value is not None else "").strip()
        # 必填项不允许留空
        if self.required and not val:
            return False, "该项为必填项，不能留空"
        if not val:
            return True, ""
        # 选项类字段：允许大小写差异的宽松匹配
        if self.options and val not in self.options:
            lowered = {o.casefold(): o for o in self.options}
            if val.casefold() not in lowered:
                return False, f"请选择以下选项之一：{', '.join(self.options)}"
        # 页面自带的 HTML pattern 校验
        if self.pattern:
            try:
                if re.fullmatch(self.pattern, val) is None:
                    return False, self.format_hint or f"格式应匹配 {self.pattern}"
            except re.error:
                # 网页上残缺的 pattern 不能中断整通电话
                pass
        kind = self.input_type.lower()
        # 邮箱格式校验
        if kind == "email" and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", val) is None:
            return False, self.format_hint or "请输入有效邮箱，例如 name@example.com"
        # 电话号码格式校验
        if kind in {"tel", "phone"} and re.fullmatch(r"[+()\d][+()\d .-]{5,24}", val) is None:
            return False, self.format_hint or "请输入包含区号的有效电话号码"
        # 日期格式校验
        if kind == "date" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", val) is None:
            return False, self.format_hint or "日期格式应为 YYYY-MM-DD"
        # 数字类型校验
        if kind == "number":
            try:
                float(val)
            except ValueError:
                return False, self.format_hint or "请输入数字"
        return True, ""


@dataclass
class AgentMessage:
    """消息总线上的点对点信封：发送方、接收方、类型与负载。"""

    sender: str
    recipient: str
    type: str
    payload: Dict[str, Any]
    sequence: int = 0
    monotonic_seconds: float = 0.0
    wall_time: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionRecord:
    """一次自主决策的完整记录：页面观察、模型选择与 provider 凭据元数据。"""

    page_url: str
    page_title: str
    known_fields: List[str]
    discovered_fields: List[FieldSpec]
    tool_called: Optional[str]
    purpose: str
    required_info: List[FieldSpec]
    rationale_summary: str
    model: str
    monotonic_seconds: float
    provider: str = ""
    provider_response_id: Optional[str] = None
    provider_usage: Dict[str, int] = field(default_factory=dict)
    wall_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data
