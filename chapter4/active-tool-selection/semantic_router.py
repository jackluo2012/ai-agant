"""
用于工具发现的层次化语义路由。

实现一个两阶段算法，将工具请求匹配到相关工具：
1. 服务器级路由：按领域/平台过滤候选服务器
2. 工具级路由：在选定服务器内按语义相似度对工具排序

这种方法在保持精度的同时降低了搜索复杂度，灵感来自 MCP-Zero。
"""

from typing import List, Dict, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from tool_knowledge_base import ServerDefinition, ToolDefinition
import config


class SemanticRouter:
    """用于工具发现的层次化语义路由。"""

    def __init__(self, servers: List[ServerDefinition]):
        self.servers = servers
        self.server_vectorizer = TfidfVectorizer(stop_words='english')
        self.tool_vectorizers: Dict[str, TfidfVectorizer] = {}

        # 预计算服务器嵌入
        self._build_server_index()

        # 预计算每个服务器的工具嵌入
        self._build_tool_indices()
    
    def _build_server_index(self):
        """为服务器构建 TF-IDF 索引。"""
        server_descriptions = [f"{s.name} {s.description}" for s in self.servers]
        self.server_embeddings = self.server_vectorizer.fit_transform(server_descriptions)

    def _build_tool_indices(self):
        """为每个服务器内的工具构建 TF-IDF 索引。"""
        for server in self.servers:
            if not server.tools:
                continue

            tool_descriptions = [
                f"{tool.name} {tool.description}"
                for tool in server.tools
            ]

            vectorizer = TfidfVectorizer(stop_words='english')
            embeddings = vectorizer.fit_transform(tool_descriptions)

            self.tool_vectorizers[server.name] = vectorizer

            # 在服务器上存储嵌入以供后续使用
            server._tool_embeddings = embeddings
    
    def route_request(self, tool_request: str, top_k_servers: int = None,
                      top_k_tools: int = None) -> List[ToolDefinition]:
        """
        使用层次化语义匹配将工具请求路由到相关工具。

        Args:
            tool_request: 所需工具的自然语言描述
            top_k_servers: 要搜索的顶部服务器数量（默认从配置获取）
            top_k_tools: 每个服务器返回的工具数量（默认从配置获取）

        Returns:
            按相关性排序的相关工具列表
        """
        if top_k_servers is None:
            top_k_servers = config.TOP_K_SERVERS
        if top_k_tools is None:
            top_k_tools = config.TOP_K_TOOLS

        # 阶段 1：服务器级路由
        relevant_servers = self._route_to_servers(tool_request, top_k_servers)

        # 阶段 2：选定服务器内的工具级路由
        relevant_tools = []
        for server, server_score in relevant_servers:
            tools_with_scores = self._route_to_tools(server, tool_request, top_k_tools)

            # 合并服务器和工具得分
            for tool, tool_score in tools_with_scores:
                combined_score = 0.3 * server_score + 0.7 * tool_score
                relevant_tools.append((tool, combined_score))

        # 按综合得分排序并按阈值过滤
        relevant_tools.sort(key=lambda x: x[1], reverse=True)
        relevant_tools = [
            (tool, score) for tool, score in relevant_tools
            if score >= config.SIMILARITY_THRESHOLD
        ]

        # 返回顶部工具
        return [tool for tool, _ in relevant_tools[:top_k_tools * top_k_servers]]
    
    def retrieve(self, query: str, top_k: int) -> List[ToolDefinition]:
        """
        跨所有服务器的平面 top-k 工具检索（单次 RAG 式路由）。

        与 ``route_request``（首先缩小到少数候选服务器）不同，此方法对每个
        服务器中的每个工具进行评分并返回全局 top-k。这是"将工具选择转化为
        知识检索"的最直接体现：给定任务描述，仅获取最可能相关的少量工具。

        Args:
            query: 自然语言任务/请求描述
            top_k: 要返回的工具数量

        Returns:
            按综合（服务器 + 工具）相似度排序的最多 ``top_k`` 个工具。
        """
        # 对每个服务器进行评分，以免过早过滤掉任何候选工具。
        relevant_servers = self._route_to_servers(query, len(self.servers))

        scored_tools = []
        for server, server_score in relevant_servers:
            for tool, tool_score in self._route_to_tools(server, query, len(server.tools)):
                combined_score = 0.3 * server_score + 0.7 * tool_score
                scored_tools.append((tool, combined_score))

        scored_tools.sort(key=lambda x: x[1], reverse=True)
        return [tool for tool, _ in scored_tools[:top_k]]

    def _route_to_servers(self, request: str, top_k: int) -> List[Tuple[ServerDefinition, float]]:
        """
        阶段 1：将请求路由到 top-k 相关服务器。

        Args:
            request: 工具请求描述
            top_k: 要返回的顶部服务器数量

        Returns:
            (服务器, 相似度得分) 元组列表
        """
        # 将请求向量化
        request_vector = self.server_vectorizer.transform([request])

        # 计算与所有服务器的相似度
        similarities = cosine_similarity(request_vector, self.server_embeddings)[0]

        # 获取 top-k 服务器
        top_indices = np.argsort(similarities)[::-1][:top_k]

        return [(self.servers[idx], similarities[idx]) for idx in top_indices]
    
    def _route_to_tools(self, server: ServerDefinition, request: str,
                        top_k: int) -> List[Tuple[ToolDefinition, float]]:
        """
        阶段 2：将请求路由到服务器内的 top-k 相关工具。

        Args:
            server: 要搜索的服务器
            request: 工具请求描述
            top_k: 要返回的顶部工具数量

        Returns:
            (工具, 相似度得分) 元组列表
        """
        if server.name not in self.tool_vectorizers:
            return []

        vectorizer = self.tool_vectorizers[server.name]
        tool_embeddings = server._tool_embeddings

        # 将请求向量化
        request_vector = vectorizer.transform([request])

        # 计算与该服务器中所有工具的相似度
        similarities = cosine_similarity(request_vector, tool_embeddings)[0]

        # 获取 top-k 工具
        top_indices = np.argsort(similarities)[::-1][:top_k]

        return [(server.tools[idx], similarities[idx]) for idx in top_indices]
    
    def get_routing_details(self, tool_request: str, top_k_servers: int = None,
                           top_k_tools: int = None) -> Dict:
        """
        获取详细的路由信息用于调试/可视化。

        返回包含以下内容的字典：
        - request: 原始请求
        - stage1_servers: 带得分的服务器列表
        - stage2_tools: 每个服务器带得分的工具列表
        - final_tools: 最终排序的工具列表
        """
        if top_k_servers is None:
            top_k_servers = config.TOP_K_SERVERS
        if top_k_tools is None:
            top_k_tools = config.TOP_K_TOOLS

        # 阶段 1：服务器路由
        relevant_servers = self._route_to_servers(tool_request, top_k_servers)

        # 阶段 2：工具路由
        stage2_results = {}
        all_tools = []

        for server, server_score in relevant_servers:
            tools_with_scores = self._route_to_tools(server, tool_request, top_k_tools)
            stage2_results[server.name] = {
                'server_score': server_score,
                'tools': [(tool.name, tool_score) for tool, tool_score in tools_with_scores]
            }

            # 计算综合得分
            for tool, tool_score in tools_with_scores:
                combined_score = 0.3 * server_score + 0.7 * tool_score
                all_tools.append((tool, combined_score, server.name))

        # 排序和过滤
        all_tools.sort(key=lambda x: x[1], reverse=True)
        final_tools = [
            {'name': tool.name, 'server': server, 'score': score}
            for tool, score, server in all_tools[:top_k_tools * top_k_servers]
            if score >= config.SIMILARITY_THRESHOLD
        ]

        return {
            'request': tool_request,
            'stage1_servers': [
                {'name': s.name, 'score': score}
                for s, score in relevant_servers
            ],
            'stage2_tools': stage2_results,
            'final_tools': final_tools
        }


class StructuredRequestParser:
    """
    解析来自 LLM 的结构化工具请求。

    MCP-Zero 使用以下格式的结构化请求：
    <tool_request>
    server: [平台/领域描述]
    tool: [操作描述]
    </tool_request>
    """
    
    @staticmethod
    def parse_request(text: str) -> Dict[str, str]:
        """
        从文本解析结构化工具请求。

        返回包含 'server' 和 'tool' 字段的字典，如果未找到则返回 None。
        """
        if '<tool_request>' not in text or '</tool_request>' not in text:
            return None
        
        start = text.find('<tool_request>')
        end = text.find('</tool_request>')
        request_text = text[start + len('<tool_request>'):end].strip()
        
        result = {}
        for line in request_text.split('\n'):
            line = line.strip()
            if line.startswith('server:'):
                result['server'] = line[7:].strip()
            elif line.startswith('tool:'):
                result['tool'] = line[5:].strip()
        
        return result if 'server' in result and 'tool' in result else None
    
    @staticmethod
    def format_request(server_desc: str, tool_desc: str) -> str:
        """格式化结构化工具请求。"""
        return f"""<tool_request>
server: {server_desc}
tool: {tool_desc}
</tool_request>"""
