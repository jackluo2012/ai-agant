"""
GraphRAG (基于图的检索增强生成) 实现
===================================

创建具有实体、关系和社区检测的知识图谱。
"""

import os
import sys
import json
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, asdict
import numpy as np
from tqdm import tqdm
import networkx as nx
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from loguru import logger
import re
from collections import defaultdict

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
    from config import GraphRAGConfig
except ImportError:
    get_llm_client = None
    GraphRAGConfig = None

from sentence_transformers import SentenceTransformer


@dataclass
class Entity:
    """知识图谱中的实体"""
    id: str
    name: str
    type: str
    description: str
    embedding: Optional[np.ndarray]
    attributes: Dict[str, Any]


@dataclass
class Relationship:
    """实体之间的关系"""
    id: str
    source: str  # 实体 ID
    target: str  # 实体 ID
    type: str
    description: str
    weight: float = 1.0


@dataclass
class Community:
    """相关实体的社区"""
    id: str
    entity_ids: List[str]
    summary: str
    embedding: Optional[np.ndarray]
    level: int


class GraphRAGIndexer:
    """GraphRAG 知识图谱索引器，支持实体抽取和社区检测"""

    def __init__(self, config: GraphRAGConfig):
        self.config = config
        # 使用统一 LLM 客户端
        self.client = get_llm_client() if get_llm_client else None
        self.model_name = self.client.model_name if self.client else "unknown"

        # 本地嵌入模型
        self.embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

        # 知识图谱组件
        self.entities: Dict[str, Entity] = {}
        self.relationships: List[Relationship] = []
        self.communities: Dict[str, Community] = {}
        self.graph = nx.Graph()

        # 确保目录存在
        self.config.index_dir.mkdir(parents=True, exist_ok=True)
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"GraphRAG 索引器初始化完成，模型: {self.model_name}")

    def chunk_text(self, text: str) -> List[str]:
        """将文本分割成带重叠的分块"""
        # 先按句子分割以更好地保留上下文
        sentences = re.split(r'(?<=[.!?。！？])\s+', text)

        chunks = []
        current_chunk = []
        current_size = 0

        for sentence in sentences:
            words = sentence.split()
            if current_size + len(words) > self.config.chunk_size:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                # 开始新分块，带重叠
                overlap: List[str] = []
                overlap_size = 0
                for prev in reversed(current_chunk):
                    prev_size = len(prev.split())
                    if overlap_size + prev_size > self.config.chunk_overlap:
                        break
                    overlap.insert(0, prev)
                    overlap_size += prev_size
                current_chunk = overlap
                current_size = overlap_size

            current_chunk.append(sentence)
            current_size += len(words)

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        logger.info(f"创建了 {len(chunks)} 个文本分块")
        return chunks

    def extract_entities_relationships(self, text: str) -> Tuple[List[Dict], List[Dict]]:
        """使用 LLM 从文本中抽取实体和关系"""
        prompt = f"""
        请从以下关于 Intel x86/x64 架构的技术文本中抽取实体和关系。

        重点关注：
        - 指令（type: "instruction"）
        - 寄存器（type: "register"）
        - CPU 特性（type: "feature"）
        - 架构组件（type: "component"）
        - 数据类型（type: "datatype"）

        关系类型：uses（使用）、modifies（修改）、depends_on（依赖）、part_of（组成部分）等。

        文本: {text[:2000]}

        请返回 JSON 格式结果：
        {{
            "entities": [
                {{"name": "实体名", "type": "实体类型", "description": "简短描述"}}
            ],
            "relationships": [
                {{"source": "实体1", "target": "实体2", "type": "关系类型", "description": "简短描述"}}
            ]
        }}

        只返回有效的 JSON，不要包含额外文本。
        """

        if not self.client:
            return [], []

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个分析技术文档并抽取结构化知识的专家。"
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=self.config.temperature
            )

            result = response.choices[0].message.content.strip()
            # 从响应中提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("entities", []), data.get("relationships", [])
            else:
                logger.warning("无法从 LLM 响应解析 JSON")
                return [], []

        except Exception as e:
            logger.error(f"抽取实体时出错: {e}")
            return [], []

    def build_knowledge_graph(self, text: str):
        """从文本构建知识图谱"""
        logger.info("正在构建知识图谱...")

        # 分块文本
        chunks = self.chunk_text(text)

        # 从每个分块抽取实体和关系
        all_entities = {}
        all_relationships = []

        for i, chunk in enumerate(tqdm(chunks, desc="抽取实体")):
            entities, relationships = self.extract_entities_relationships(chunk)

            # 处理实体
            for entity_data in entities:
                entity_name = entity_data.get("name", "").lower()
                if entity_name and entity_name not in all_entities:
                    # 为实体描述创建嵌入
                    desc = entity_data.get("description", entity_name)
                    embedding = self.embedding_model.encode([desc])[0]

                    entity = Entity(
                        id=f"entity_{len(all_entities)}",
                        name=entity_name,
                        type=entity_data.get("type", "unknown"),
                        description=desc,
                        embedding=embedding,
                        attributes={"chunk_id": i}
                    )
                    all_entities[entity_name] = entity
                    self.entities[entity.id] = entity

            # 处理关系
            for rel_data in relationships:
                source_name = rel_data.get("source", "").lower()
                target_name = rel_data.get("target", "").lower()

                if source_name in all_entities and target_name in all_entities:
                    relationship = Relationship(
                        id=f"rel_{len(all_relationships)}",
                        source=all_entities[source_name].id,
                        target=all_entities[target_name].id,
                        type=rel_data.get("type", "related"),
                        description=rel_data.get("description", ""),
                        weight=1.0
                    )
                    all_relationships.append(relationship)
                    self.relationships.append(relationship)

        # 构建 NetworkX 图
        logger.info("正在构建 NetworkX 图...")
        for entity_id, entity in self.entities.items():
            self.graph.add_node(entity_id, **asdict(entity))

        for rel in self.relationships:
            self.graph.add_edge(
                rel.source, rel.target,
                type=rel.type,
                description=rel.description,
                weight=rel.weight
            )

        logger.info(f"知识图谱构建完成，共 {len(self.entities)} 个实体，{len(self.relationships)} 条关系")

    def detect_communities(self):
        """检测知识图谱中的社区"""
        logger.info("正在检测社区...")

        if len(self.graph.nodes) == 0:
            logger.warning("图为空，无法检测社区")
            return

        # 使用不同的社区检测算法
        if self.config.community_detection_algorithm == "leiden":
            try:
                import leidenalg
                import igraph as ig

                # 将 NetworkX 转换为 igraph
                ig_graph = ig.Graph.from_networkx(self.graph)
                partitions = leidenalg.find_partition(ig_graph, leidenalg.ModularityVertexPartition)
                communities = {}
                for i, community in enumerate(partitions):
                    communities[i] = [list(self.graph.nodes())[idx] for idx in community]
            except ImportError:
                logger.warning("Leiden 算法不可用，回退到 Louvain")
                communities = nx.community.louvain_communities(self.graph, seed=42)
                communities = {i: list(comm) for i, comm in enumerate(communities)}
        else:
            # 使用 Louvain 算法
            communities = nx.community.louvain_communities(self.graph, seed=42)
            communities = {i: list(comm) for i, comm in enumerate(communities)}

        # 创建社区摘要
        for comm_id, entity_ids in communities.items():
            if not entity_ids:
                continue

            # 获取社区中的实体
            community_entities = [self.entities[eid] for eid in entity_ids if eid in self.entities]

            # 创建社区摘要
            entity_descriptions = [e.description for e in community_entities[:10]]
            summary_prompt = f"""
            请总结以下来自 Intel x86/x64 文档的相关实体组：

            实体：
            {chr(10).join(entity_descriptions)}

            请提供简洁摘要（最多 150 词），描述这些实体的共同点及其在架构中的作用。
            """

            if not self.client:
                summary = f"包含 {len(entity_ids)} 个相关实体的社区"
            else:
                try:
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": "你是一个总结技术文档的专家。"},
                            {"role": "user", "content": summary_prompt}
                        ],
                        max_tokens=200,
                        temperature=self.config.temperature
                    )
                    summary = response.choices[0].message.content.strip()
                except Exception as e:
                    logger.error(f"创建社区摘要时出错: {e}")
                    summary = f"包含 {len(entity_ids)} 个相关实体的社区"

            # 为社区创建嵌入
            embedding = self.embedding_model.encode([summary])[0]

            community = Community(
                id=f"community_{comm_id}",
                entity_ids=entity_ids,
                summary=summary,
                embedding=embedding,
                level=0
            )
            self.communities[community.id] = community

        logger.info(f"检测到 {len(self.communities)} 个社区")

    def hierarchical_summarization(self):
        """创建社区的层次摘要"""
        if len(self.communities) <= 1:
            return

        logger.info("正在创建层次社区摘要...")

        # 按相似度对社区进行分组
        community_ids = list(self.communities.keys())
        community_embeddings = np.array([self.communities[cid].embedding for cid in community_ids])
        similarity_matrix = cosine_similarity(community_embeddings)

        # 简单的层次聚类
        threshold = 0.7
        merged_communities = []
        processed = set()

        for i, comm_id in enumerate(community_ids):
            if comm_id in processed:
                continue

            # 查找相似社区
            similar = []
            for j, other_id in enumerate(community_ids):
                if i != j and similarity_matrix[i][j] > threshold:
                    similar.append(other_id)
                    processed.add(other_id)

            if similar:
                # 合并社区
                merged_ids = [comm_id] + similar
                all_entities = []
                for mid in merged_ids:
                    all_entities.extend(self.communities[mid].entity_ids)

                # 创建合并摘要
                summaries = [self.communities[mid].summary for mid in merged_ids]
                merge_prompt = f"""
                请将以下相关社区摘要合并为更高级别的摘要：

                {chr(10).join(summaries)}

                请提供简洁摘要（最多 200 词），描述整体主题。
                """

                if not self.client:
                    merged_summary = f"包含 {len(all_entities)} 个实体的高级社区"
                else:
                    try:
                        response = self.client.chat.completions.create(
                            model=self.model_name,
                            messages=[
                                {"role": "system", "content": "你是一个创建层次摘要的专家。"},
                                {"role": "user", "content": merge_prompt}
                            ],
                            max_tokens=250,
                            temperature=self.config.temperature
                        )
                        merged_summary = response.choices[0].message.content.strip()
                    except Exception as e:
                        logger.error(f"创建合并摘要时出错: {e}")
                        merged_summary = f"包含 {len(all_entities)} 个实体的高级社区"

                # 创建新社区
                merged_embedding = self.embedding_model.encode([merged_summary])[0]
                merged_community = Community(
                    id=f"merged_community_{len(merged_communities)}",
                    entity_ids=all_entities,
                    summary=merged_summary,
                    embedding=merged_embedding,
                    level=1
                )
                self.communities[merged_community.id] = merged_community
                merged_communities.append(merged_community)

        logger.info(f"创建了 {len(merged_communities)} 个层次社区")

    def search(self, query: str, top_k: int = 5, search_type: str = "hybrid") -> List[Dict[str, Any]]:
        """
        搜索知识图谱

        Args:
            query: 搜索查询
            top_k: 返回结果数量
            search_type: "entity"、"community" 或 "hybrid"
        """
        query_embedding = self.embedding_model.encode([query])[0]
        results = []

        if search_type in ["entity", "hybrid"]:
            # 搜索实体
            entity_scores = []
            for entity_id, entity in self.entities.items():
                if entity.embedding is not None:
                    score = cosine_similarity([query_embedding], [entity.embedding])[0][0]
                    entity_scores.append((entity_id, score))

            entity_scores.sort(key=lambda x: x[1], reverse=True)

            for entity_id, score in entity_scores[:top_k]:
                entity = self.entities[entity_id]

                # 获取相关实体
                neighbors = list(self.graph.neighbors(entity_id)) if entity_id in self.graph else []

                results.append({
                    "type": "entity",
                    "id": entity_id,
                    "name": entity.name,
                    "entity_type": entity.type,
                    "description": entity.description,
                    "score": float(score),
                    "related_entities": neighbors[:5]
                })

        if search_type in ["community", "hybrid"]:
            # 搜索社区
            community_scores = []
            for comm_id, community in self.communities.items():
                if community.embedding is not None:
                    score = cosine_similarity([query_embedding], [community.embedding])[0][0]
                    community_scores.append((comm_id, score))

            community_scores.sort(key=lambda x: x[1], reverse=True)

            for comm_id, score in community_scores[:top_k]:
                community = self.communities[comm_id]

                # 获取社区中的样本实体
                sample_entities = []
                for entity_id in community.entity_ids[:5]:
                    if entity_id in self.entities:
                        entity = self.entities[entity_id]
                        sample_entities.append({
                            "name": entity.name,
                            "type": entity.type
                        })

                results.append({
                    "type": "community",
                    "id": comm_id,
                    "summary": community.summary,
                    "level": community.level,
                    "score": float(score),
                    "entity_count": len(community.entity_ids),
                    "sample_entities": sample_entities
                })

        # 按分数排序所有结果
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def multi_hop_search(self, start_entity: str, max_hops: int = 2,
                         relation_filter: Optional[str] = None,
                         top_k: int = 10) -> List[Dict[str, Any]]:
        """
        多跳关系检索：沿知识图谱的关系边遍历，回答「A 通过什么与 B 相连」这类
        扁平向量检索无法表达的关系性问题。

        与 search() 的区别：search() 只按嵌入相似度召回孤立的实体/社区，
        而本方法真正利用图结构，返回从起始实体出发的关系路径。

        Args:
            start_entity: 起始实体名（不区分大小写，按子串匹配）
            max_hops: 最大跳数
            relation_filter: 若指定，只保留终点边为该关系类型的路径
            top_k: 返回的路径数上限

        Returns:
            每条路径形如 {"target", "target_type", "hops", "path"}
            path 是若干 {"source", "relation", "target"} 步骤
        """
        # 按名字子串匹配定位起始节点
        start_id = None
        needle = start_entity.lower()
        for entity_id, entity in self.entities.items():
            if needle in entity.name.lower():
                start_id = entity_id
                break
        if start_id is None or start_id not in self.graph:
            logger.warning(f"multi_hop_search: 未找到起始实体 '{start_entity}'")
            return []

        # BFS 沿边遍历，收集 <= max_hops 跳的路径
        results: List[Dict[str, Any]] = []
        queue = [(start_id, [])]
        while queue and len(results) < top_k * 4:
            node_id, path = queue.pop(0)
            if len(path) >= max_hops:
                continue
            for neighbor in self.graph.neighbors(node_id):
                rel_type = self.graph[node_id][neighbor].get("type", "related")
                src_name = self.entities[node_id].name if node_id in self.entities else node_id
                dst_name = self.entities[neighbor].name if neighbor in self.entities else neighbor
                step = {"source": src_name, "relation": rel_type, "target": dst_name}
                new_path = path + [step]
                if relation_filter is None or rel_type == relation_filter:
                    results.append({
                        "target": dst_name,
                        "target_type": self.entities[neighbor].type if neighbor in self.entities else "unknown",
                        "hops": len(new_path),
                        "path": new_path,
                    })
                queue.append((neighbor, new_path))

        results.sort(key=lambda r: r["hops"])
        return results[:top_k]

    def save_index(self, path: Optional[Path] = None):
        """将知识图谱索引保存到磁盘"""
        save_path = path or self.config.index_dir / "graphrag_index.pkl"

        # 转换为可序列化格式
        index_data = {
            'entities': {eid: asdict(e) for eid, e in self.entities.items()},
            'relationships': [asdict(r) for r in self.relationships],
            'communities': {cid: asdict(c) for cid, c in self.communities.items()},
            'graph': nx.node_link_data(self.graph),
            'config': asdict(self.config)
        }

        # 将 numpy 数组转换为列表
        for entity in index_data['entities'].values():
            if entity['embedding'] is not None:
                entity['embedding'] = entity['embedding'].tolist()

        for community in index_data['communities'].values():
            if community['embedding'] is not None:
                community['embedding'] = community['embedding'].tolist()

        with open(save_path, 'wb') as f:
            pickle.dump(index_data, f)

        logger.info(f"GraphRAG 索引已保存到 {save_path}")

    def load_index(self, path: Optional[Path] = None):
        """从磁盘加载知识图谱索引"""
        load_path = path or self.config.index_dir / "graphrag_index.pkl"

        with open(load_path, 'rb') as f:
            index_data = pickle.load(f)

        # 重建实体
        self.entities = {}
        for eid, entity_dict in index_data['entities'].items():
            if entity_dict['embedding'] is not None:
                entity_dict['embedding'] = np.array(entity_dict['embedding'])
            self.entities[eid] = Entity(**entity_dict)

        # 重建关系
        self.relationships = [Relationship(**r) for r in index_data['relationships']]

        # 重建社区
        self.communities = {}
        for cid, comm_dict in index_data['communities'].items():
            if comm_dict['embedding'] is not None:
                comm_dict['embedding'] = np.array(comm_dict['embedding'])
            self.communities[cid] = Community(**comm_dict)

        # 重建图
        self.graph = nx.node_link_graph(index_data['graph'])

        logger.info(f"从 {load_path} 加载了 GraphRAG 索引")

    def get_graph_statistics(self) -> Dict[str, Any]:
        """获取知识图谱的统计信息"""
        entity_types = defaultdict(int)
        for entity in self.entities.values():
            entity_types[entity.type] += 1

        rel_types = defaultdict(int)
        for rel in self.relationships:
            rel_types[rel.type] += 1

        return {
            "total_entities": len(self.entities),
            "total_relationships": len(self.relationships),
            "total_communities": len(self.communities),
            "entity_types": dict(entity_types),
            "relationship_types": dict(rel_types),
            "graph_density": nx.density(self.graph) if len(self.graph) > 0 else 0,
            "average_degree": sum(dict(self.graph.degree()).values()) / max(1, len(self.graph.nodes))
        }
