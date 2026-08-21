"""
用于捕获和存储浏览器操作序列的工作流数据结构。

本模块定义用于表示学习工作流的结构，
包括单个步骤和完整的操作序列。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
import json


class ActionType(Enum):
    """可以在工作流中记录的动作类型"""
    NAVIGATE = "navigate"
    CLICK = "click"
    INPUT_TEXT = "input_text"
    SELECT_OPTION = "select_option"
    SCROLL = "scroll"
    WAIT = "wait"
    SWITCH_TAB = "switch_tab"
    CLOSE_TAB = "close_tab"
    UPLOAD_FILE = "upload_file"


class PredicateType(Enum):
    """机器可检查的浏览器状态谓词。"""
    URL_CONTAINS = "url_contains"
    ELEMENT_VISIBLE = "element_visible"
    ELEMENT_TEXT_CONTAINS = "element_text_contains"
    ELEMENT_VALUE_EQUALS = "element_value_equals"
    PAGE_STATE_EQUALS = "page_state_equals"


class WorkflowStatus(Enum):
    """工作流验证状态"""
    CANDIDATE = "candidate"      # 待验证（首次探索后）
    VALIDATED = "validated"      # 已验证（通过完整回放）
    INVALID = "invalid"          # 失效（页面变化导致谓词失败）


@dataclass
class StatePredicate:
    """前置条件、后置条件或最终状态断言。"""

    predicate_type: PredicateType
    expected: Any = True
    selector: Optional[str] = None
    state_key: Optional[str] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "predicate_type": self.predicate_type.value,
            "expected": self.expected,
            "selector": self.selector,
            "state_key": self.state_key,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StatePredicate':
        values = dict(data)
        values["predicate_type"] = PredicateType(values["predicate_type"])
        return cls(**values)


@dataclass
class WorkflowStep:
    """表示工作流中的单个步骤"""

    action_type: ActionType

    # 用于元素识别的稳定选择器
    xpath: Optional[str] = None
    css_selector: Optional[str] = None

    # 动作参数
    parameters: Dict[str, Any] = field(default_factory=dict)

    # 额外上下文
    element_attributes: Dict[str, str] = field(default_factory=dict)
    description: str = ""

    # 时间信息
    wait_before: float = 0.0  # 执行此步骤前等待的秒数
    timeout: float = 15.0  # 等待元素准备就绪的最长时间

    # 验证
    expected_outcome: Optional[str] = None
    preconditions: List[StatePredicate] = field(default_factory=list)
    postconditions: List[StatePredicate] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """将步骤转换为字典以进行序列化"""
        return {
            "action_type": self.action_type.value,
            "xpath": self.xpath,
            "css_selector": self.css_selector,
            "parameters": self.parameters,
            "element_attributes": self.element_attributes,
            "description": self.description,
            "wait_before": self.wait_before,
            "timeout": self.timeout,
            "expected_outcome": self.expected_outcome,
            "preconditions": [p.to_dict() for p in self.preconditions],
            "postconditions": [p.to_dict() for p in self.postconditions],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowStep':
        """从字典创建步骤"""
        values = dict(data)
        values["action_type"] = ActionType(values["action_type"])
        values["preconditions"] = [StatePredicate.from_dict(p) for p in values.get("preconditions", [])]
        values["postconditions"] = [StatePredicate.from_dict(p) for p in values.get("postconditions", [])]
        return cls(**values)


@dataclass
class Workflow:
    """
    表示从浏览器操作序列中学习的完整工作流。

    工作流生命周期：
    1. candidate（候选）：首次探索后创建，需要验证
    2. validated（已验证）：通过完整回放验证，可复用
    3. invalid（失效）：页面变化导致谓词失败，需要重新学习
    """

    workflow_id: str = ""
    intent: str = ""
    description: str = ""
    initial_url: Optional[str] = None

    # 工作流步骤
    steps: List[WorkflowStep] = field(default_factory=list)

    # 元数据
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_modified: str = field(default_factory=lambda: datetime.now().isoformat())
    validation_status: WorkflowStatus = WorkflowStatus.CANDIDATE

    # 性能指标
    success_count: int = 0
    failure_count: int = 0
    total_execution_time: float = 0.0

    # 示例参数（用于参数化）
    example_parameters: Dict[str, Any] = field(default_factory=dict)

    # 最终状态谓词
    final_predicates: List[StatePredicate] = field(default_factory=list)

    def add_step(self, step: WorkflowStep) -> None:
        """向工作流添加步骤"""
        self.steps.append(step)
        self.last_modified = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """将工作流转换为字典以进行序列化"""
        return {
            "workflow_id": self.workflow_id,
            "intent": self.intent,
            "description": self.description,
            "initial_url": self.initial_url,
            "steps": [step.to_dict() for step in self.steps],
            "created_at": self.created_at,
            "last_modified": self.last_modified,
            "validation_status": self.validation_status.value,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_execution_time": self.total_execution_time,
            "example_parameters": self.example_parameters,
            "final_predicates": [p.to_dict() for p in self.final_predicates],
        }

    def to_json(self) -> str:
        """将工作流序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Workflow':
        """从字典创建工作流"""
        values = dict(data)
        values["validation_status"] = WorkflowStatus(values.get("validation_status", "candidate"))
        values["steps"] = [WorkflowStep.from_dict(step) for step in values.get("steps", [])]
        values["final_predicates"] = [
            StatePredicate.from_dict(p) for p in values.get("final_predicates", [])
        ]
        return cls(**values)

    @classmethod
    def from_json(cls, json_str: str) -> 'Workflow':
        """从 JSON 字符串创建工作流"""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def mark_validated(self) -> None:
        """将工作流标记为已验证"""
        self.validation_status = WorkflowStatus.VALIDATED
        self.last_modified = datetime.now().isoformat()

    def parameterize(self, parameters: Dict[str, Any]) -> 'Workflow':
        """
        使用给定参数创建参数化的工作流副本。

        Args:
            parameters: 参数字典，键对应占位符（如 {recipient}）

        Returns:
            参数化的工作流副本
        """
        import copy
        param_workflow = copy.deepcopy(self)

        # 应用参数到每个步骤
        for step in param_workflow.steps:
            for key, value in step.parameters.items():
                if isinstance(value, str):
                    # 替换参数占位符
                    for param_key, param_value in parameters.items():
                        placeholder = f"{{{param_key}}}"
                        if placeholder in value:
                            step.parameters[key] = value.replace(placeholder, str(param_value))

        return param_workflow
