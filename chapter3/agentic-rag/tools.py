"""知识库交互工具"""

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

import json
import logging
import requests
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from config import KnowledgeBaseConfig, KnowledgeBaseType


logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """知识库搜索结果"""
    doc_id: str
    chunk_id: str
    text: str
    score: float
    metadata: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "text": self.text,
            "score": self.score,
            "metadata": self.metadata or {}
        }


class KnowledgeBaseTools:
    """知识库交互工具"""

    def __init__(self, config: KnowledgeBaseConfig):
        self.config = config
        self.document_store = {}  # 内存中的文档存储
        self._offline_retriever = None  # 延迟构建的进程内 BM25 索引

        # 加载文档存储（如果存在）
        try:
            with open(config.document_store_path, 'r', encoding='utf-8') as f:
                self.document_store = json.load(f)
        except FileNotFoundError:
            logger.info("未找到现有文档存储，将从头开始")
        except Exception as e:
            logger.error(f"加载文档存储时出错: {e}")

    def save_document_store(self):
        """保存文档存储到磁盘"""
        try:
            with open(self.config.document_store_path, 'w', encoding='utf-8') as f:
                json.dump(self.document_store, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存文档存储时出错: {e}")

    def knowledge_base_search(self, query: str) -> List[Dict[str, Any]]:
        """
        使用自然语言查询搜索知识库

        Args:
            query: 自然语言查询字符串

        Returns:
            匹配的文档分块列表（含得分）
        """
        try:
            if self.config.type == KnowledgeBaseType.OFFLINE:
                return self._search_offline(query)
            elif self.config.type == KnowledgeBaseType.LOCAL:
                return self._search_local(query)
            elif self.config.type == KnowledgeBaseType.DIFY:
                return self._search_dify(query)
            else:
                raise ValueError(f"不支持的知识库类型: {self.config.type}")
        except Exception as e:
            logger.error(f"知识库搜索出错: {e}")
            return []

    def _get_offline_retriever(self):
        """延迟构建本地语料库的进程内 BM25 检索器"""
        if self._offline_retriever is None:
            from offline_retriever import OfflineRetriever
            self._offline_retriever = OfflineRetriever(self.config.offline_corpus_path)
        return self._offline_retriever

    def _search_offline(self, query: str) -> List[Dict[str, Any]]:
        """搜索进程内 BM25 索引（无需服务器/API 密钥）"""
        retriever = self._get_offline_retriever()
        results = retriever.search(query, self.config.offline_top_k)
        logger.info(f"离线 BM25 搜索返回 {len(results)} 个结果")
        return results

    def _search_local(self, query: str) -> List[Dict[str, Any]]:
        """使用本地检索流水线搜索"""
        try:
            response = requests.post(
                f"{self.config.local_base_url}/search",
                json={
                    "query": query,
                    "mode": "hybrid",
                    "top_k": self.config.local_top_k,
                    "rerank": True
                }, timeout=30
            )
            response.raise_for_status()

            results = []
            data = response.json()

            # 检索流水线根据模式返回不同键的结果
            # 对于混合模式，我们想要 reranked_results
            search_results = data.get("reranked_results", [])

            # 如果没有重排序结果，回退到 dense 或 sparse 结果
            if not search_results:
                search_results = data.get("dense_results", [])
            if not search_results:
                search_results = data.get("sparse_results", [])

            for item in search_results:
                # 从结果中提取 doc_id 和 chunk_id
                doc_id = item.get("doc_id", "")
                chunk_id = item.get("chunk_id", f"{doc_id}_chunk_{len(results)}")

                # 根据结果类型获取文本字段和得分
                text = item.get("text", "")
                score = item.get("rerank_score", item.get("score", 0.0))

                result = SearchResult(
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    text=text,
                    score=score,
                    metadata=item.get("metadata", {})
                )
                results.append(result.to_dict())

            logger.info(f"本地搜索返回 {len(results)} 个结果")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"连接本地检索流水线出错: {e}")
            return []

    def _search_dify(self, query: str) -> List[Dict[str, Any]]:
        """使用 Dify API 搜索"""
        if not self.config.dify_api_key:
            logger.error("未配置 Dify API 密钥")
            return []

        try:
            headers = {
                "Authorization": f"Bearer {self.config.dify_api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "query": query,
                "top_k": self.config.dify_top_k
            }

            if self.config.dify_dataset_id:
                payload["dataset_id"] = self.config.dify_dataset_id

            response = requests.post(
                f"{self.config.dify_base_url}/datasets/search",
                headers=headers,
                json=payload, timeout=30
            )
            response.raise_for_status()

            results = []
            data = response.json()

            for item in data.get("data", {}).get("records", []):
                doc_id = item.get("document_id", "")
                chunk_id = item.get("segment_id", f"{doc_id}_chunk_{len(results)}")

                result = SearchResult(
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    text=item.get("content", ""),
                    score=item.get("score", 0.0),
                    metadata=item.get("metadata", {})
                )
                results.append(result.to_dict())

            logger.info(f"Dify 搜索返回 {len(results)} 个结果")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"连接 Dify API 出错: {e}")
            return []

    def get_document(self, doc_id: str) -> Dict[str, Any]:
        """
        从知识库检索完整文档

        Args:
            doc_id: 文档 ID

        Returns:
            完整的文档内容和元数据
        """
        try:
            # 首先检查本地文档存储
            if doc_id in self.document_store:
                return self.document_store[doc_id]

            if self.config.type == KnowledgeBaseType.OFFLINE:
                return self._get_offline_retriever().get_document(doc_id)
            elif self.config.type == KnowledgeBaseType.LOCAL:
                return self._get_document_local(doc_id)
            elif self.config.type == KnowledgeBaseType.DIFY:
                return self._get_document_dify(doc_id)
            else:
                raise ValueError(f"不支持的知识库类型: {self.config.type}")
        except Exception as e:
            logger.error(f"检索文档 {doc_id} 时出错: {e}")
            return {"error": f"未找到文档 {doc_id}"}

    def _get_document_local(self, doc_id: str) -> Dict[str, Any]:
        """从本地检索流水线获取文档"""
        try:
            response = requests.get(
                f"{self.config.local_base_url}/documents/{doc_id}", timeout=30
            )

            if response.status_code == 404:
                return {"error": f"未找到文档 {doc_id}"}

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"从本地流水线获取文档出错: {e}")
            return {"error": str(e)}

    def _get_document_dify(self, doc_id: str) -> Dict[str, Any]:
        """从 Dify 获取文档"""
        if not self.config.dify_api_key:
            return {"error": "未配置 Dify API 密钥"}

        try:
            headers = {
                "Authorization": f"Bearer {self.config.dify_api_key}",
                "Content-Type": "application/json"
            }

            response = requests.get(
                f"{self.config.dify_base_url}/documents/{doc_id}",
                headers=headers, timeout=30
            )

            if response.status_code == 404:
                return {"error": f"未找到文档 {doc_id}"}

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"从 Dify 获取文档出错: {e}")
            return {"error": str(e)}

    def add_document(self, doc_id: str, content: str, metadata: Optional[Dict] = None):
        """添加文档到本地存储"""
        self.document_store[doc_id] = {
            "doc_id": doc_id,
            "content": content,
            "metadata": metadata or {}
        }
        self.save_document_store()


# Agent 工具函数定义
def get_tool_definitions() -> List[Dict[str, Any]]:
    """获取 OpenAI 格式的工具定义"""
    return [
        {
            "type": "function",
            "function": {
                "name": "knowledge_base_search",
                "description": "使用自然语言查询搜索知识库中的相关信息。返回最匹配的文档分块。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "用于查找相关信息的自然语言搜索查询"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_document",
                "description": "使用文档 ID 从知识库检索特定文档的完整内容。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_id": {
                            "type": "string",
                            "description": "要检索的文档的唯一标识符"
                        }
                    },
                    "required": ["doc_id"]
                }
            }
        }
    ]
