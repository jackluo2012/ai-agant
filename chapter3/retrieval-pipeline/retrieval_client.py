"""稠密和稀疏嵌入服务的通信客户端。"""

import httpx
import asyncio
from typing import Dict, Any, List, Optional, Tuple
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    """嵌入服务的统一搜索结果。"""
    doc_id: str
    score: float
    text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    source: str = ""  # "dense" 或 "sparse"
    rank: Optional[int] = None
    debug_info: Optional[Dict[str, Any]] = None

class RetrievalClient:
    """并行检索稠密和稀疏服务的客户端。"""

    def __init__(self, dense_url: str, sparse_url: str, timeout: float = 30.0):
        """初始化检索客户端。

        Args:
            dense_url: 稠密嵌入服务URL
            sparse_url: 稀疏嵌入服务URL
            timeout: 请求超时时间（秒）
        """
        self.dense_url = dense_url.rstrip('/')
        self.sparse_url = sparse_url.rstrip('/')
        self.timeout = timeout

    async def index_document_dense(self, text: str, doc_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """在稠密嵌入服务中索引文档。

        Args:
            text: 文档文本
            doc_id: 文档ID
            metadata: 可选的元数据

        Returns:
            索引结果字典
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                payload = {
                    "text": text,
                    "doc_id": doc_id,
                    "metadata": metadata or {}
                }
                response = await client.post(f"{self.dense_url}/index", json=payload)
                response.raise_for_status()
                result = response.json()
                logger.debug(f"文档 {doc_id} 稠密索引成功")
                return result
            except Exception as e:
                logger.error(f"文档 {doc_id} 稠密索引失败: {e}")
                return {"success": False, "error": str(e)}

    async def index_document_sparse(self, text: str, doc_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """在稀疏嵌入服务中索引文档。

        Args:
            text: 文档文本
            doc_id: 文档ID
            metadata: 可选的元数据

        Returns:
            索引结果字典
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # 稀疏服务现在直接接受 doc_id
                payload = {
                    "text": text,
                    "doc_id": doc_id,  # 直接传递 doc_id
                    "metadata": metadata or {}
                }

                response = await client.post(f"{self.sparse_url}/index", json=payload)
                response.raise_for_status()
                result = response.json()
                logger.debug(f"文档 {doc_id} 稀疏索引成功")
                return result
            except Exception as e:
                logger.error(f"文档 {doc_id} 稀疏索引失败: {e}")
                return {"success": False, "error": str(e)}

    async def index_document(self, text: str, doc_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """在两个服务中并行索引文档。

        Args:
            text: 文档文本
            doc_id: 文档ID
            metadata: 可选的元数据

        Returns:
            包含两个服务索引结果的字典
        """
        logger.info(f"正在并行索引文档 {doc_id}...")

        # 并行执行两个索引操作
        dense_task = self.index_document_dense(text, doc_id, metadata)
        sparse_task = self.index_document_sparse(text, doc_id, metadata)

        dense_result, sparse_result = await asyncio.gather(dense_task, sparse_task)

        return {
            "doc_id": doc_id,
            "dense": dense_result,
            "sparse": sparse_result,
            "success": dense_result.get("success", False) and sparse_result.get("success", False)
        }

    async def search_dense(self, query: str, top_k: int = 20) -> List[SearchResult]:
        """使用稠密嵌入搜索。

        Args:
            query: 搜索查询
            top_k: 返回结果数量

        Returns:
            SearchResult 对象列表
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                payload = {
                    "query": query,
                    "top_k": top_k,
                    "return_documents": True
                }
                response = await client.post(f"{self.dense_url}/search", json=payload)
                response.raise_for_status()
                data = response.json()

                results = []
                for item in data.get("results", []):
                    results.append(SearchResult(
                        doc_id=item["doc_id"],
                        score=item["score"],
                        text=item.get("text"),
                        metadata=item.get("metadata"),
                        source="dense",
                        rank=item.get("rank"),
                        debug_info={
                            "original_score": item["score"],
                            "original_rank": item.get("rank", 0)
                        }
                    ))

                logger.debug(f"稠密搜索返回 {len(results)} 个结果")
                return results

            except Exception as e:
                logger.error(f"稠密搜索失败: {e}")
                return []

    async def search_sparse(self, query: str, top_k: int = 20) -> List[SearchResult]:
        """使用稀疏嵌入（BM25）搜索。

        Args:
            query: 搜索查询
            top_k: 返回结果数量

        Returns:
            SearchResult 对象列表
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                payload = {
                    "query": query,
                    "top_k": top_k
                }
                response = await client.post(f"{self.sparse_url}/search", json=payload)
                response.raise_for_status()
                data = response.json()

                results = []
                for idx, item in enumerate(data):
                    # 现在稀疏服务直接返回 doc_id
                    doc_id = item.get("doc_id", f"doc_{idx}")

                    results.append(SearchResult(
                        doc_id=doc_id,
                        score=item["score"],
                        text=item.get("text"),
                        metadata=item.get("metadata"),
                        source="sparse",
                        rank=idx + 1,
                        debug_info={
                            "bm25_score": item["score"],
                            "matched_terms": item.get("debug", {}).get("matched_terms", []) if item.get("debug") else [],
                            "doc_length": item.get("debug", {}).get("doc_length", 0) if item.get("debug") else 0,
                            "original_rank": idx + 1
                        }
                    ))

                logger.debug(f"稀疏搜索返回 {len(results)} 个结果")
                return results

            except Exception as e:
                logger.error(f"稀疏搜索失败: {e}")
                return []

    async def search(self, query: str, top_k: int = 20, mode: str = "hybrid") -> Tuple[List[SearchResult], List[SearchResult]]:
        """使用指定模式搜索。

        Args:
            query: 搜索查询
            top_k: 返回结果数量
            mode: 搜索模式（dense、sparse 或 hybrid）

        Returns:
            (稠密结果, 稀疏结果) 元组
        """
        logger.info(f"正在搜索，模式: {mode}, 查询: '{query[:50]}...'")

        dense_results = []
        sparse_results = []

        if mode == "dense":
            dense_results = await self.search_dense(query, top_k)
        elif mode == "sparse":
            sparse_results = await self.search_sparse(query, top_k)
        elif mode == "hybrid":
            # 并行执行两个搜索
            dense_task = self.search_dense(query, top_k)
            sparse_task = self.search_sparse(query, top_k)
            dense_results, sparse_results = await asyncio.gather(dense_task, sparse_task)
        else:
            raise ValueError(f"无效的搜索模式: {mode}")

        return dense_results, sparse_results

    async def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """从两个服务中删除文档。

        Args:
            doc_id: 要删除的文档ID

        Returns:
            删除结果字典
        """
        logger.info(f"正在从两个服务中删除文档 {doc_id}...")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # 从稠密服务删除
            dense_task = client.delete(f"{self.dense_url}/index", json={"doc_id": doc_id})

            # 对于稀疏服务，检查是否支持删除
            # 如果不支持，需要重建索引
            sparse_task = client.delete(f"{self.sparse_url}/index")  # 暂时清空全部

            try:
                dense_response, sparse_response = await asyncio.gather(dense_task, sparse_task)
                return {
                    "doc_id": doc_id,
                    "dense": dense_response.json() if dense_response.status_code == 200 else {"success": False},
                    "sparse": sparse_response.json() if sparse_response.status_code == 200 else {"success": False}
                }
            except Exception as e:
                logger.error(f"删除文档 {doc_id} 失败: {e}")
                return {"success": False, "error": str(e)}
