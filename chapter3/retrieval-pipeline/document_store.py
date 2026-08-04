"""检索流水线的文档存储模块。"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class DocumentStore:
    """用于教学目的的内存文档存储。"""

    def __init__(self):
        self.documents: Dict[str, Dict[str, Any]] = {}
        self.metadata_index: Dict[str, List[str]] = {}  # 按元数据字段索引

    def add_document(self, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """添加文档到存储。

        Args:
            doc_id: 文档ID
            text: 文档文本内容
            metadata: 可选的元数据字典
        """
        self.documents[doc_id] = {
            "doc_id": doc_id,
            "text": text,
            "metadata": metadata or {},
            "indexed_at": datetime.now().isoformat()
        }

        # 更新元数据索引
        if metadata:
            for key, value in metadata.items():
                if key not in self.metadata_index:
                    self.metadata_index[key] = []
                if doc_id not in self.metadata_index[key]:
                    self.metadata_index[key].append(doc_id)

        logger.debug(f"文档 {doc_id} 已添加到存储")

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取文档。

        Args:
            doc_id: 文档ID

        Returns:
            文档字典，不存在则返回 None
        """
        return self.documents.get(doc_id)

    def get_documents(self, doc_ids: List[str]) -> List[Dict[str, Any]]:
        """批量获取文档。

        Args:
            doc_ids: 文档ID列表

        Returns:
            文档字典列表
        """
        docs = []
        for doc_id in doc_ids:
            doc = self.get_document(doc_id)
            if doc:
                docs.append(doc)
        return docs

    def delete_document(self, doc_id: str) -> bool:
        """从存储中删除文档。

        Args:
            doc_id: 要删除的文档ID

        Returns:
            删除成功返回 True，文档不存在返回 False
        """
        if doc_id in self.documents:
            doc = self.documents[doc_id]

            # 从元数据索引中移除
            if doc.get("metadata"):
                for key in doc["metadata"]:
                    if key in self.metadata_index and doc_id in self.metadata_index[key]:
                        self.metadata_index[key].remove(doc_id)
                        if not self.metadata_index[key]:
                            del self.metadata_index[key]

            del self.documents[doc_id]
            logger.debug(f"文档 {doc_id} 已从存储中删除")
            return True
        return False

    def list_documents(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """列出文档，支持分页。

        Args:
            limit: 返回的文档数量限制
            offset: 起始偏移量

        Returns:
            文档字典列表
        """
        doc_ids = list(self.documents.keys())[offset:offset + limit]
        return [self.documents[doc_id] for doc_id in doc_ids]

    def clear(self) -> None:
        """清空所有文档。"""
        self.documents.clear()
        self.metadata_index.clear()
        logger.info("存储中所有文档已清空")

    def size(self) -> int:
        """获取文档数量。

        Returns:
            文档总数
        """
        return len(self.documents)

    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计信息。

        Returns:
            包含统计信息的字典
        """
        return {
            "total_documents": self.size(),
            "metadata_fields": list(self.metadata_index.keys()),
            "metadata_distribution": {
                key: len(values) for key, values in self.metadata_index.items()
            }
        }
