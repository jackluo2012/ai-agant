"""用户记忆评估框架的数据模型。"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class MessageRole(str, Enum):
    """对话中的消息角色。"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class RubricGrade(str, Enum):
    """实验 6-3 使用的四个具体等级。"""

    EXCELLENT = "excellent"
    GOOD = "good"
    PASS = "pass"
    FAIL = "fail"


class RubricDimensionResult(BaseModel):
    """单个评分维度可审计的评分和引用证据。"""

    grade: RubricGrade
    score: int = Field(ge=1, le=4)
    reasoning: str
    evidence: List[str] = Field(default_factory=list)
    boundary_case: Optional[str] = None


class HallucinationResult(BaseModel):
    """基于事实的判定。``detected`` 是无条件的评分否决。"""

    detected: bool
    claims: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    reasoning: str


class ConversationMessage(BaseModel):
    """对话中的单条消息。"""
    role: MessageRole
    content: str

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {"role": self.role.value, "content": self.content}


class ConversationHistory(BaseModel):
    """包含多条消息的对话历史。"""
    conversation_id: str = Field(description="对话的唯一标识符")
    timestamp: str = Field(description="对话的时间戳")
    messages: List[ConversationMessage] = Field(description="对话中的消息列表")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="关于对话的额外元数据")

    @property
    def rounds(self) -> int:
        """获取对话轮数（用户-助手对数）。"""
        user_messages = sum(1 for msg in self.messages if msg.role == MessageRole.USER)
        return user_messages

    def validate_rounds(self, min_rounds: int = 45) -> bool:
        """验证对话是否至少具有所需的最小轮数。"""
        return self.rounds >= min_rounds


class TestCase(BaseModel):
    """记忆评估的单个测试用例。"""
    test_id: str = Field(description="测试用例的唯一标识符")
    category: str = Field(description="测试类别（layer1、layer2 或 layer3）")
    title: str = Field(description="测试用例的标题")
    description: str = Field(description="测试用例评估内容的描述")
    conversation_histories: List[ConversationHistory] = Field(description="先前的对话历史")
    user_question: str = Field(description="新对话中用户的问题")
    evaluation_criteria: str = Field(description="评估响应的文本标准")
    expected_behavior: Optional[str] = Field(default=None, description="代理的预期行为（可选）")

    def validate(self) -> bool:
        """验证测试用例结构。"""
        # 检查类别
        if self.category not in ["layer1", "layer2", "layer3"]:
            return False

        # 检查对话历史要求
        if self.category == "layer1" and len(self.conversation_histories) != 1:
            return False
        elif self.category in ["layer2", "layer3"] and len(self.conversation_histories) < 2:
            return False

        # 验证每个对话至少有 10 轮
        for history in self.conversation_histories:
            if not history.validate_rounds(10):
                return False

        return True


class EvaluationResult(BaseModel):
    """代理响应的评估结果。"""
    test_id: str = Field(description="测试用例 ID")
    reward: float = Field(description="连续奖励分数（0.0-1.0）")
    passed: Optional[bool] = Field(default=None, description="可选的二进制通过/失败，用于向后兼容")
    reasoning: str = Field(description="评估的详细推理")
    required_info_found: Dict[str, float] = Field(description="每个所需信息项的分数（0.0-1.0）")
    suggestions: Optional[str] = Field(default=None, description="改进建议")
    dimensions: Dict[str, RubricDimensionResult] = Field(
        default_factory=dict,
        description="实验 6-3 评分标准结果：precision、recall、reasoning 和 proactivity",
    )
    hallucination: Optional[HallucinationResult] = Field(
        default=None,
        description="基于事实的判定；检测到幻觉会将奖励强制为零",
    )
    veto_applied: bool = Field(default=False, description="是否应用了幻觉否决")

    def to_summary(self) -> str:
        """生成评估结果的摘要。"""
        # 如果未明确设置，则根据奖励阈值确定通过/失败
        if self.passed is not None:
            status = "通过" if self.passed else "失败"
        else:
            # 使用 0.6 作为向后兼容的默认阈值
            status = "通过" if self.reward >= 0.6 else "失败"
        summary = f"测试 {self.test_id}: {status}（奖励：{self.reward:.2f}）\n"
        summary += f"推理：{self.reasoning}\n"
        if self.suggestions:
            summary += f"建议：{self.suggestions}\n"
        return summary


class TestSuite(BaseModel):
    """测试用例集合。"""
    name: str = Field(description="测试套件名称")
    version: str = Field(description="测试套件版本")
    test_cases: List[TestCase] = Field(description="测试用例列表")

    def get_by_category(self, category: str) -> List[TestCase]:
        """获取特定类别中的所有测试用例。"""
        return [tc for tc in self.test_cases if tc.category == category]

    def get_by_id(self, test_id: str) -> Optional[TestCase]:
        """通过 ID 获取特定测试用例。"""
        for tc in self.test_cases:
            if tc.test_id == test_id:
                return tc
        return None
