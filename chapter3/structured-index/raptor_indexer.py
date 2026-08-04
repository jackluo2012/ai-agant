"""
RAPTOR (递归抽象处理与树组织检索) 实现
=====================================

创建具有递归摘要的层次树结构。
"""

import os
import sys
import json
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import numpy as np
from tqdm import tqdm
import tiktoken
from sklearn.mixture import GaussianMixture
from sklearn.metrics.pairwise import cosine_similarity
import umap
from sentence_transformers import SentenceTransformer
from loguru import logger

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from llm.client import get_llm_client
    from config import RaptorConfig
except ImportError:
    get_llm_client = None
    RaptorConfig = None


@dataclass
class TreeNode:
    """RAPTOR 树中的节点"""
    id: str
    level: int
    text: str
    summary: str
    embedding: Optional[np.ndarray]
    children: List[str]  # 子节点的 ID
    parent: Optional[str]  # 父节点的 ID


class RaptorIndexer:
    """RAPTOR 层次树文档索引器，支持递归摘要"""

    def __init__(self, config: RaptorConfig):
        self.config = config
        # 使用统一 LLM 客户端
        self.client = get_llm_client() if get_llm_client else None
        self.model_name = self.client.model_name if self.client else "unknown"

        # 本地嵌入模型
        self.embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        try:
            self.tokenizer = tiktoken.encoding_for_model(self.model_name)
        except KeyError:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")

        # 树结构
        self.nodes: Dict[str, TreeNode] = {}
        self.root_nodes: List[str] = []

        # 确保索引目录存在
        self.config.index_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"RAPTOR 索引器初始化完成，模型: {self.model_name}")

    def chunk_text(self, text: str) -> List[str]:
        """将文本分割成带重叠的分块"""
        words = text.split()
        chunks = []
        step = max(1, self.config.chunk_size - self.config.chunk_overlap)

        for i in range(0, len(words), step):
            chunk = " ".join(words[i:i + self.config.chunk_size])
            if chunk:
                chunks.append(chunk)

        logger.info(f"创建了 {len(chunks)} 个文本分块")
        return chunks

    def create_embeddings(self, texts: List[str]) -> np.ndarray:
        """使用 sentence transformers 创建文本嵌入"""
        embeddings = self.embedding_model.encode(texts, show_progress_bar=True)
        return np.array(embeddings)

    def summarize_text(self, text: str, max_length: int = 200) -> str:
        """使用 LLM API 摘要文本"""
        if not self.client:
            # 回退到截断
            words = text.split()[:max_length]
            return " ".join(words) + "..."

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个善于创建简洁摘要的助手，专注于关键技术信息。"
                    },
                    {
                        "role": "user",
                        "content": f"请用不超过 {max_length} 个词总结以下文本，重点关注主要技术概念和重要细节：\n\n{text}"
                    }
                ],
                max_tokens=max_length * 2,
                temperature=self.config.temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"摘要文本时出错: {e}")
            # 回退到截断
            words = text.split()[:max_length]
            return " ".join(words) + "..."

    def cluster_nodes(self, embeddings: np.ndarray, min_clusters: int = 2, max_clusters: int = 10) -> np.ndarray:
        """使用高斯混合模型聚类嵌入向量"""
        n_samples = len(embeddings)
        n_clusters = min(max(min_clusters, n_samples // 5), min(max_clusters, n_samples))

        if n_samples < 2:
            return np.zeros(n_samples)

        # 如需要，使用 UMAP 进行降维
        if embeddings.shape[1] > 50:
            reducer = umap.UMAP(n_components=50, n_neighbors=min(15, n_samples-1))
            embeddings_reduced = reducer.fit_transform(embeddings)
        else:
            embeddings_reduced = embeddings

        # 执行聚类
        gmm = GaussianMixture(n_components=n_clusters, random_state=42)
        cluster_labels = gmm.fit_predict(embeddings_reduced)

        return cluster_labels

    def build_tree_level(self, node_ids: List[str]) -> List[str]:
        """通过聚类和摘要节点构建树的一层"""
        if len(node_ids) <= 1:
            return node_ids

        # 获取节点的嵌入
        texts = [self.nodes[nid].text for nid in node_ids]
        embeddings = np.array([self.nodes[nid].embedding for nid in node_ids])

        # 聚类节点
        cluster_labels = self.cluster_nodes(embeddings)

        # 按聚类分组节点
        clusters: Dict[int, List[str]] = {}
        for i, label in enumerate(cluster_labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(node_ids[i])

        # 为每个聚类创建父节点
        parent_ids = []
        current_level = self.nodes[node_ids[0]].level + 1

        for cluster_id, child_ids in clusters.items():
            # 合并子节点的文本
            combined_text = "\n\n".join([self.nodes[cid].text for cid in child_ids])

            # 为父节点创建摘要
            summary = self.summarize_text(combined_text, self.config.summarization_length)

            # 为摘要创建嵌入
            summary_embedding = self.embedding_model.encode([summary])[0]

            # 创建父节点
            parent_id = f"level{current_level}_cluster{cluster_id}"
            parent_node = TreeNode(
                id=parent_id,
                level=current_level,
                text=summary,
                summary=summary,
                embedding=summary_embedding,
                children=child_ids,
                parent=None
            )

            # 更新子节点以引用父节点
            for child_id in child_ids:
                self.nodes[child_id].parent = parent_id

            self.nodes[parent_id] = parent_node
            parent_ids.append(parent_id)

        logger.info(f"在层级 {current_level} 创建了 {len(parent_ids)} 个父节点")
        return parent_ids

    def build_index(self, text: str):
        """从文本构建 RAPTOR 树索引"""
        logger.info("正在构建 RAPTOR 树索引...")

        # 分块文本
        chunks = self.chunk_text(text)

        # 从分块创建叶节点
        logger.info("正在创建叶节点...")
        leaf_ids = []
        for i, chunk in enumerate(tqdm(chunks, desc="处理分块")):
            # 创建嵌入
            embedding = self.embedding_model.encode([chunk])[0]

            # 为分块创建摘要
            summary = self.summarize_text(chunk, max_length=100)

            # 创建叶节点
            node_id = f"leaf_{i}"
            node = TreeNode(
                id=node_id,
                level=0,
                text=chunk,
                summary=summary,
                embedding=embedding,
                children=[],
                parent=None
            )
            self.nodes[node_id] = node
            leaf_ids.append(node_id)

        # 构建树层级
        current_level_ids = leaf_ids
        for level in range(self.config.tree_depth):
            if len(current_level_ids) <= 1:
                break

            logger.info(f"正在构建树层级 {level + 1}...")
            current_level_ids = self.build_tree_level(current_level_ids)

        self.root_nodes = current_level_ids
        logger.info(f"RAPTOR 树构建完成，共 {len(self.nodes)} 个节点，{len(self.root_nodes)} 个根节点")

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索 RAPTOR 树获取相关信息"""
        # 创建查询嵌入
        query_embedding = self.embedding_model.encode([query])[0]

        # 计算与所有节点的相似度
        similarities = []
        for node_id, node in self.nodes.items():
            if node.embedding is not None:
                sim = cosine_similarity([query_embedding], [node.embedding])[0][0]
                similarities.append((node_id, sim))

        # 按相似度排序
        similarities.sort(key=lambda x: x[1], reverse=True)

        # 获取 top-k 结果，包含不同层级以增加多样性
        results = []
        levels_seen = set()

        for node_id, score in similarities:
            node = self.nodes[node_id]

            # 通过包含不同层级的节点增加多样性
            if len(results) < top_k:
                results.append({
                    "node_id": node_id,
                    "level": node.level,
                    "text": node.text,
                    "summary": node.summary,
                    "score": float(score)
                })
                levels_seen.add(node.level)
            elif node.level not in levels_seen and len(results) < top_k * 2:
                # 包含一些来自其他层级的多样性结果
                results.append({
                    "node_id": node_id,
                    "level": node.level,
                    "text": node.text,
                    "summary": node.summary,
                    "score": float(score)
                })
                levels_seen.add(node.level)

        return results[:top_k]

    def save_index(self, path: Optional[Path] = None):
        """将 RAPTOR 树索引保存到磁盘"""
        save_path = path or self.config.index_dir / "raptor_index.pkl"

        # 将节点转换为可序列化格式
        serializable_nodes = {}
        for node_id, node in self.nodes.items():
            node_dict = asdict(node)
            # 将 numpy 数组转换为列表以便 JSON 序列化
            if node.embedding is not None:
                node_dict['embedding'] = node.embedding.tolist()
            serializable_nodes[node_id] = node_dict

        index_data = {
            'nodes': serializable_nodes,
            'root_nodes': self.root_nodes,
            'config': asdict(self.config)
        }

        with open(save_path, 'wb') as f:
            pickle.dump(index_data, f)

        logger.info(f"RAPTOR 索引已保存到 {save_path}")

    def load_index(self, path: Optional[Path] = None):
        """从磁盘加载 RAPTOR 树索引"""
        load_path = path or self.config.index_dir / "raptor_index.pkl"

        with open(load_path, 'rb') as f:
            index_data = pickle.load(f)

        # 重建节点
        self.nodes = {}
        for node_id, node_dict in index_data['nodes'].items():
            # 将列表转换回 numpy 数组
            if node_dict['embedding'] is not None:
                node_dict['embedding'] = np.array(node_dict['embedding'])
            self.nodes[node_id] = TreeNode(**node_dict)

        self.root_nodes = index_data['root_nodes']
        logger.info(f"从 {load_path} 加载了 RAPTOR 索引")

    def get_tree_statistics(self) -> Dict[str, Any]:
        """获取 RAPTOR 树的统计信息"""
        level_counts = {}
        for node in self.nodes.values():
            if node.level not in level_counts:
                level_counts[node.level] = 0
            level_counts[node.level] += 1

        return {
            "total_nodes": len(self.nodes),
            "root_nodes": len(self.root_nodes),
            "levels": len(level_counts),
            "nodes_per_level": level_counts,
            "average_children": sum(len(n.children) for n in self.nodes.values()) / max(1, len(self.nodes))
        }
