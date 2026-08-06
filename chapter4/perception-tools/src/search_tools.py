"""
搜索工具模块

提供网络搜索、知识库搜索和文件下载功能。

此模块包含：
- search_web: 使用 DuckDuckGo 进行免费网络搜索
- download_file: 从 URL 下载文件到本地
- search_knowledge_base: 搜索本地知识库目录

所有功能都免费且无需 API 密钥。
"""
import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Union

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mcp.types import TextContent
from pydantic import BaseModel, Field

# 添加项目根目录到路径，用于导入统一 LLM 客户端
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from base import ActionResponse, is_url, download_file_from_url


load_dotenv()


class SearchResult(BaseModel):
    """
    单个搜索结果的结构化数据

    属性:
        id: 结果唯一标识符
        title: 结果标题
        url: 结果链接
        snippet: 结果摘要片段
        source: 搜索来源（如 duckduckgo）
    """

    id: str
    title: str
    url: str
    snippet: str
    source: str


class SearchMetadata(BaseModel):
    """
    搜索操作的元数据

    属性:
        query: 搜索查询字符串
        search_engine: 使用的搜索引擎
        total_results: 返回结果总数
        search_time: 搜索耗时（秒）
        language: 搜索语言
        country: 搜索区域
    """

    query: str
    search_engine: str
    total_results: int
    search_time: float | None = None
    language: str = "zh-CN"  # 默认中文
    country: str = "cn"      # 默认中国


async def search_web(
    query: str,
    num_results: int = 5,
    region: str = "wt-wt"
) -> Union[str, TextContent]:
    """
    使用 DuckDuckGo 进行网络搜索（免费，无需 API 密钥）

    通过 DuckDuckGo HTML 版本进行搜索，解析返回的 HTML 获取结果。

    Args:
        query: 搜索查询字符串
        num_results: 返回的结果数量（1-10），默认 5
        region: 区域代码（如：'cn-zh'、'us-en'、'wt-wt' 全球）

    Returns:
        包含搜索结果的 TextContent

    示例:
        >>> results = await search_web("Python 编程", num_results=3)
        >>> results['query']
        'Python 编程'
        >>> results['count']
        3
    """
    try:
        # 验证输入
        if not query or not query.strip():
            raise ValueError("搜索查询不能为空")

        validated_num_results = max(1, min(num_results, 10))

        logging.info(f"🔍 正在搜索：'{query}'")
        start_time = time.time()

        # 使用 DuckDuckGo HTML 版本进行搜索
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        data = {
            "q": query.strip(),
            "kl": region
        }

        response = requests.post(url, data=data, headers=headers, timeout=15)
        response.raise_for_status()

        search_time = time.time() - start_time

        # 解析 HTML 结果
        soup = BeautifulSoup(response.text, 'html.parser')
        result_divs = soup.find_all('div', class_='result')

        search_results = []
        for i, result_div in enumerate(result_divs[:validated_num_results]):
            try:
                # 提取标题和 URL
                title_tag = result_div.find('a', class_='result__a')
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)
                url_link = title_tag.get('href', '')

                # 提取摘要片段
                snippet_tag = result_div.find('a', class_='result__snippet')
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

                result = SearchResult(
                    id=f"ddg-{i}",
                    title=title,
                    url=url_link,
                    snippet=snippet,
                    source="duckduckgo"
                )
                search_results.append(result)
            except Exception as e:
                logging.warning(f"解析搜索结果 {i} 时出错：{e}")
                continue

        # 构建元数据
        metadata = SearchMetadata(
            query=query,
            search_engine="duckduckgo",
            total_results=len(search_results),
            search_time=search_time,
            language="zh-CN",
            country=region
        )

        # 格式化输出内容
        formatted_content = {
            "query": query,
            "results": [result.model_dump() for result in search_results],
            "count": len(search_results)
        }

        logging.info(f"✅ 在 {search_time:.2f} 秒内找到 {len(search_results)} 个结果")

        action_response = ActionResponse(
            success=True,
            message=formatted_content,
            metadata=metadata.model_dump()
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"搜索操作失败：{str(e)}"
        logging.error(f"搜索错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "search_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def download_file(
    url: str,
    output_path: str,
    overwrite: bool = False,
    timeout: int = 180
) -> Union[str, TextContent]:
    """
    从 URL 下载文件到本地存储

    支持流式下载大文件，自动创建目标目录。

    Args:
        url: 下载来源 URL
        output_path: 保存文件的本地路径
        overwrite: 是否覆盖现有文件，默认 False
        timeout: 下载超时时间（秒），默认 180 秒

    Returns:
        包含下载结果的 TextContent

    Raises:
        ValueError: URL 格式不正确或文件已存在且未启用覆盖

    示例:
        >>> result = await download_file(
        ...     "https://example.com/file.pdf",
        ...     "/tmp/file.pdf",
        ...     overwrite=True
        ... )
        >>> result['success']
        True
    """
    try:
        # 验证 URL 格式
        if not url.startswith(("http://", "https://")):
            raise ValueError("仅支持 HTTP/HTTPS URL")

        output_file = Path(output_path).expanduser().resolve()

        # 检查文件是否已存在
        if output_file.exists() and not overwrite:
            raise ValueError(
                f"文件已存在：{output_file}。"
                f"使用 overwrite=True 替换。"
            )

        # 创建目标目录
        output_file.parent.mkdir(parents=True, exist_ok=True)

        logging.info(f"📥 正在从以下位置下载：{url}")
        start_time = time.time()

        # 下载文件到临时位置
        temp_path, content = download_file_from_url(url, timeout=timeout)

        # 移动到最终目标
        with open(output_file, 'wb') as f:
            f.write(content)

        # 清理临时文件
        Path(temp_path).unlink(missing_ok=True)

        duration = time.time() - start_time
        file_size = len(content)

        logging.info(
            f"✅ 在 {duration:.2f} 秒内下载了 "
            f"{file_size / 1024:.2f} KB"
        )

        action_response = ActionResponse(
            success=True,
            message=f"成功将文件下载到 {output_file}",
            metadata={
                "url": url,
                "output_path": str(output_file),
                "file_size_bytes": file_size,
                "duration_seconds": duration
            }
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"下载失败：{str(e)}"
        logging.error(f"下载错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "download_error", "url": url}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def search_knowledge_base(
    query: str,
    knowledge_base_path: str,
    top_k: int = 5
) -> Union[str, TextContent]:
    """
    搜索本地知识库目录

    使用简单的文本匹配在本地文件中搜索查询内容。

    Args:
        query: 搜索查询字符串
        knowledge_base_path: 知识库目录路径
        top_k: 返回的顶部结果数量，默认 5

    Returns:
        包含搜索结果的 TextContent

    注意:
        - 支持的文件类型：.txt, .md, .json
        - 使用简单的字符串匹配，非向量搜索

    示例:
        >>> results = await search_knowledge_base(
        ...     "Python 教程",
        ...     "/path/to/knowledge",
        ...     top_k=3
        ... )
    """
    try:
        kb_path = Path(knowledge_base_path).expanduser().resolve()

        # 验证知识库路径
        if not kb_path.exists():
            raise FileNotFoundError(f"未找到知识库：{kb_path}")

        if not kb_path.is_dir():
            raise ValueError(f"知识库路径必须是目录：{kb_path}")

        logging.info(f"🔍 正在搜索知识库：{kb_path}")

        # 简单文件搜索 - 查找包含查询的文件
        results = []
        query_lower = query.lower()

        # 支持的文件类型
        supported_extensions = [".txt", ".md", ".json", ".py", ".js", ".html"]

        for file_path in kb_path.rglob("*"):
            if file_path.is_file() and file_path.suffix in supported_extensions:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    if query_lower in content.lower():
                        # 获取第一次出现位置周围的片段
                        idx = content.lower().index(query_lower)
                        start = max(0, idx - 100)
                        end = min(len(content), idx + 200)
                        snippet = content[start:end].strip()

                        results.append({
                            "file": str(file_path.relative_to(kb_path)),
                            "snippet": snippet,
                            "relevance": content.lower().count(query_lower)
                        })
                except Exception as e:
                    logging.warning(f"读取 {file_path} 时出错：{e}")
                    continue

        # 按相关性排序并限制结果数量
        results.sort(key=lambda x: x["relevance"], reverse=True)
        results = results[:top_k]

        logging.info(f"✅ 找到 {len(results)} 个结果")

        action_response = ActionResponse(
            success=True,
            message={
                "query": query,
                "results": results,
                "total_found": len(results)
            },
            metadata={
                "knowledge_base": str(kb_path),
                "top_k": top_k
            }
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"知识库搜索失败：{str(e)}"
        logging.error(f"知识库搜索错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "kb_search_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )
