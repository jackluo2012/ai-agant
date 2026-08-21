"""
用于存储和检索学习工作流的知识库。

本模块提供工作流的持久化存储和智能检索，
包括意图匹配和工作流选择。
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging
from dataclasses import dataclass
import uuid

from .workflow import Workflow, WorkflowStep, WorkflowStatus


logger = logging.getLogger(__name__)


@dataclass
class IntentMatch:
    """表示任务意图与存储工作流之间的匹配"""
    workflow: Workflow
    confidence: float  # 0.0 到 1.0
    match_reason: str


class KnowledgeBase:
    """
    管理学习工作流的存储和检索。

    知识库提供：
    - 工作流的持久化存储
    - 意图匹配以查找相关工作流
    - 性能跟踪和优化
    """

    def __init__(self, storage_path: str = "./knowledge_base"):
        """
        初始化知识库。

        Args:
            storage_path: 存储工作流数据的目录路径
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)

        # 工作流的内存缓存
        self.workflows: Dict[str, Workflow] = {}

        # 用于快速匹配的意图索引
        self.intent_index: Dict[str, List[str]] = {}  # intent -> [workflow_ids]

        # 加载现有工作流
        self.load_all_workflows()

    def save_workflow(self, workflow: Workflow) -> None:
        """
        将工作流保存到持久化存储。

        Args:
            workflow: 要保存的工作流

        Raises:
            ValueError: 如果工作流未经验证
        """
        if workflow.validation_status != WorkflowStatus.VALIDATED:
            raise ValueError(
                "只有在重置环境中通过完整回放验证的工作流才能进入能力库"
            )

        # 如果不存在则生成 ID
        if not workflow.workflow_id:
            workflow.workflow_id = str(uuid.uuid4())

        # 保存到文件
        workflow_file = self.storage_path / f"workflow_{workflow.workflow_id}.json"
        with open(workflow_file, 'w', encoding='utf-8') as f:
            f.write(workflow.to_json())

        # 更新内存缓存
        self.workflows[workflow.workflow_id] = workflow

        # 更新意图索引
        if workflow.intent not in self.intent_index:
            self.intent_index[workflow.intent] = []
        if workflow.workflow_id not in self.intent_index[workflow.intent]:
            self.intent_index[workflow.intent].append(workflow.workflow_id)

        logger.info(f"已保存工作流 '{workflow.workflow_id}'，意图：{workflow.intent}")

    def save_candidate(self, workflow: Workflow) -> None:
        """
        持久化候选工作流以供审计，但不使其可检索。

        Args:
            workflow: 要保存的候选工作流
        """
        if not workflow.workflow_id:
            workflow.workflow_id = str(uuid.uuid4())
        workflow.validation_status = WorkflowStatus.CANDIDATE
        candidate_file = self.storage_path / f"candidate_{workflow.workflow_id}.json"
        candidate_file.write_text(workflow.to_json(), encoding="utf-8")
        logger.info(f"已保存候选工作流 '{workflow.workflow_id}'")

    def publish_validated(self, workflow: Workflow) -> None:
        """
        发布已验证的工作流到可检索能力库。

        Args:
            workflow: 已验证的工作流
        """
        workflow.validation_status = WorkflowStatus.VALIDATED
        self.save_workflow(workflow)
        logger.info(f"已发布已验证工作流 '{workflow.workflow_id}'")

    def invalidate_workflow(self, workflow_id: str, reason: str = "") -> None:
        """
        将工作流标记为失效并将其移出检索。

        Args:
            workflow_id: 要失效的工作流 ID
            reason: 失效原因
        """
        if workflow_id not in self.workflows:
            logger.warning(f"工作流 '{workflow_id}' 不存在，无法标记为失效")
            return

        workflow = self.workflows[workflow_id]
        workflow.validation_status = WorkflowStatus.INVALID

        # 移出意图索引
        if workflow.intent in self.intent_index:
            self.intent_index[workflow.intent] = [
                wid for wid in self.intent_index[workflow.intent] if wid != workflow_id
            ]

        # 保存失效状态
        invalid_file = self.storage_path / f"invalid_{workflow_id}.json"
        invalid_file.write_text(workflow.to_json(), encoding="utf-8")

        # 从缓存中移除
        del self.workflows[workflow_id]

        logger.info(f"工作流 '{workflow_id}' 已标记为失效：{reason}")

    def load_all_workflows(self) -> None:
        """从存储加载所有已验证的工作流。"""
        for file_path in self.storage_path.glob("workflow_*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    workflow = Workflow.from_json(f.read())
                    self.workflows[workflow.workflow_id] = workflow

                    # 更新意图索引
                    if workflow.intent not in self.intent_index:
                        self.intent_index[workflow.intent] = []
                    if workflow.workflow_id not in self.intent_index[workflow.intent]:
                        self.intent_index[workflow.intent].append(workflow.workflow_id)

                logger.debug(f"加载工作流 '{workflow.workflow_id}'")
            except Exception as e:
                logger.error(f"加载工作流失败 {file_path}: {e}")

    def find_workflow_for_task(self, task: str) -> Optional[IntentMatch]:
        """
        查找与任务匹配的工作流。

        Args:
            task: 任务描述

        Returns:
            匹配的工作流和置信度，如果未找到则返回 None
        """
        if not self.workflows:
            return None

        best_match = None
        best_confidence = 0.0

        for workflow in self.workflows.values():
            # 简单的意图匹配（可以改进为更复杂的相似度算法）
            similarity = self._calculate_similarity(task, workflow.intent)

            if similarity > best_confidence:
                best_confidence = similarity
                best_match = workflow

        if best_match and best_confidence > 0.3:
            return IntentMatch(
                workflow=best_match,
                confidence=best_confidence,
                match_reason=f"与 '{best_match.intent}' 的意图相似度为 {best_confidence:.2f}"
            )

        return None

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本之间的简单相似度。

        Args:
            text1: 第一个文本
            text2: 第二个文本

        Returns:
            相似度分数（0.0 到 1.0）
        """
        # 简单的单词重叠相似度
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def update_workflow_metrics(
        self,
        workflow_id: str,
        success: bool,
        execution_time: float = 0.0,
        model_calls_saved: int = 0
    ) -> None:
        """
        更新工作流性能指标。

        Args:
            workflow_id: 工作流 ID
            success: 执行是否成功
            execution_time: 执行时间（秒）
            model_calls_saved: 节省的模型调用次数
        """
        if workflow_id not in self.workflows:
            return

        workflow = self.workflows[workflow_id]
        if success:
            workflow.success_count += 1
            workflow.total_execution_time += execution_time
        else:
            workflow.failure_count += 1

        workflow.last_modified = datetime.now().isoformat()

        # 持久化更新的工作流
        self.save_workflow(workflow)

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取知识库统计信息。

        Returns:
            包含统计数据的字典
        """
        total_workflows = len(self.workflows)
        total_success = sum(w.success_count for w in self.workflows.values())
        total_failures = sum(w.failure_count for w in self.workflows.values())
        total_execution_time = sum(w.total_execution_time for w in self.workflows.values())

        return {
            "total_workflows": total_workflows,
            "total_success": total_success,
            "total_failures": total_failures,
            "total_execution_time": round(total_execution_time, 2),
            "average_execution_time": round(
                total_execution_time / total_success if total_success > 0 else 0, 2
            ),
            "success_rate": round(
                total_success / (total_success + total_failures) * 100
                if (total_success + total_failures) > 0 else 0, 2
            ),
        }

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """
        通过 ID 获取工作流。

        Args:
            workflow_id: 工作流 ID

        Returns:
            工作流对象，如果未找到则返回 None
        """
        return self.workflows.get(workflow_id)

    def list_workflows(self, status: Optional[WorkflowStatus] = None) -> List[Workflow]:
        """
        列出所有工作流，可选按状态过滤。

        Args:
            status: 要过滤的工作流状态（可选）

        Returns:
            工作流列表
        """
        workflows = list(self.workflows.values())
        if status:
            workflows = [w for w in workflows if w.validation_status == status]
        return workflows
