"""
用于 Browser-Use RPA 的学习代理

一个为 browser-use 添加学习和经验回放功能的封装系统。
本代理可以从成功的任务执行中学习，并高效回放学习的工作流。
"""

from .knowledge_base import KnowledgeBase
from .workflow import Workflow, WorkflowStep, StatePredicate, PredicateType, WorkflowStatus

__all__ = [
    'LearningAgent', 'KnowledgeBase', 'Workflow', 'WorkflowStep',
    'StatePredicate', 'PredicateType', 'WorkflowStatus'
]


def __getattr__(name):
    """使数据模型可在没有 browser-use 的离线测试中使用。"""
    if name == 'LearningAgent':
        from .agent import LearningAgent
        return LearningAgent
    raise AttributeError(name)
