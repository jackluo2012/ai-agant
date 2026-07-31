"""
网页搜索和获取工具模块
======================

本模块提供网页搜索和内容获取功能。

功能:
    - 使用 Serper API 进行网络搜索
    - 网页内容抓取和文本转换
    - 页面缓存避免重复请求
    - 无 API Key 时提供模拟数据
"""

import json
import logging
import requests
from typing import List, Dict, Any
from bs4 import BeautifulSoup
import html2text
from urllib.parse import urlparse, urljoin
import time

from config import Config

# 配置日志
logger = logging.getLogger(__name__)


class WebTools:
    """
    网页工具类

    提供网络搜索和页面获取功能

    Attributes:
        serper_api_key: Serper API 密钥
        html_converter: HTML 到文本转换器
        page_cache: 页面缓存字典
    """

    def __init__(self):
        """初始化网页工具"""
        self.serper_api_key = Config.SERPER_API_KEY
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = True
        self.html_converter.ignore_emphasis = False
        self.html_converter.body_width = 0  # 不换行
        self.html_converter.single_line_break = True

        # 页面缓存，避免重复请求
        self.page_cache = {}

    def search_web(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """
        使用 Serper API 搜索网络

        Args:
            query: 搜索查询
            num_results: 返回结果数量

        Returns:
            包含搜索结果和抓取内容的字典
        """
        try:
            if not self.serper_api_key:
                # 回退到模拟结果用于演示
                logger.warning("未设置 Serper API Key，使用模拟数据")
                return self._get_mock_search_results(query)

            logger.info(f"正在搜索网络: {query}")

            # 调用 Serper API
            headers = {
                'X-API-KEY': self.serper_api_key,
                'Content-Type': 'application/json'
            }

            payload = {
                'q': query,
                'num': num_results
            }

            response = requests.post(
                f"{Config.SERPER_BASE_URL}/search",
                headers=headers,
                json=payload,
                timeout=10
            )

            if response.status_code != 200:
                logger.error(f"Serper API 错误: {response.status_code}")
                return self._get_mock_search_results(query)

            data = response.json()

            # 处理自然搜索结果
            results = []
            organic_results = data.get('organic', [])[:num_results]

            for result in organic_results:
                # 获取并转换每个页面
                url = result.get('link', '')
                if url:
                    page_content = self.fetch_webpage(url)

                    results.append({
                        'title': result.get('title', ''),
                        'url': url,
                        'snippet': result.get('snippet', ''),
                        'content': page_content.get('content', ''),
                        'content_length': len(page_content.get('content', '')),
                        'fetch_success': page_content.get('success', False)
                    })

                    # 小延迟以示尊重
                    time.sleep(0.5)

            return {
                'query': query,
                'num_results': len(results),
                'results': results,
                'timestamp': time.time()
            }

        except Exception as e:
            logger.error(f"网络搜索错误: {str(e)}")
            return self._get_mock_search_results(query)

    def fetch_webpage(self, url: str) -> Dict[str, Any]:
        """
        获取网页并转换 HTML 为文本

        Args:
            url: 网页 URL

        Returns:
            包含转换后文本内容的字典
        """
        try:
            # 检查缓存
            if url in self.page_cache:
                logger.info(f"使用缓存内容: {url}")
                return self.page_cache[url]

            logger.info(f"正在获取网页: {url}")

            # 获取页面
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            # 解析 HTML
            soup = BeautifulSoup(response.text, 'lxml')

            # 移除脚本和样式元素
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # 转换为文本
            text_content = self.html_converter.handle(str(soup))

            # 清理文本
            lines = text_content.split('\n')
            cleaned_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):  # 移除空行和导航标记
                    cleaned_lines.append(line)

            cleaned_text = '\n'.join(cleaned_lines)

            # 过长则截断
            if len(cleaned_text) > Config.MAX_WEBPAGE_LENGTH:
                cleaned_text = cleaned_text[:Config.MAX_WEBPAGE_LENGTH] + "\n\n[内容已截断...]"

            result = {
                'url': url,
                'title': soup.title.string if soup.title else '无标题',
                'content': cleaned_text,
                'content_length': len(cleaned_text),
                'success': True,
                'timestamp': time.time()
            }

            # 缓存结果
            self.page_cache[url] = result

            return result

        except Exception as e:
            logger.error(f"获取网页错误 {url}: {str(e)}")

            error_result = {
                'url': url,
                'title': '错误',
                'content': f"获取网页失败: {str(e)}",
                'content_length': 0,
                'success': False,
                'error': str(e),
                'timestamp': time.time()
            }

            # 缓存失败结果以避免重试
            self.page_cache[url] = error_result

            return error_result

    def _get_mock_search_results(self, query: str) -> Dict[str, Any]:
        """
        获取模拟搜索结果（无 API Key 时用于测试）

        Args:
            query: 搜索查询

        Returns:
            模拟搜索结果
        """
        # OpenAI 联合创始人的模拟数据
        mock_data = {
            "openai": [
                {
                    'title': 'OpenAI - 维基百科',
                    'url': 'https://zh.wikipedia.org/wiki/OpenAI',
                    'snippet': 'OpenAI 由 Sam Altman、Elon Musk、Ilya Sutskever、Greg Brockman、Wojciech Zaremba 和 John Schulman 于 2015 年创立...',
                    'content': '''OpenAI 于 2015 年 12 月由 Sam Altman、Elon Musk、Ilya Sutskever、Greg Brockman、Wojciech Zaremba 和 John Schulman 创立。

该组织的成立目标是推动数字智能发展，造福人类。

联合创始人当前状态（截至 2024 年）：
- Sam Altman: OpenAI CEO（2023 年 11 月短暂离职后回归）
- Elon Musk: 2018 年离开 OpenAI 董事会，2023 年创立 xAI
- Ilya Sutskever: 前首席科学家，2024 年 5 月离开 OpenAI，联合创立 Safe Superintelligence Inc.
- Greg Brockman: OpenAI 总裁兼董事长
- Wojciech Zaremba: OpenAI 语言和代码生成部门负责人
- John Schulman: 联合创始人，2024 年 8 月离开 OpenAI 加入 Anthropic

其他早期成员：
- Andrej Karpathy: 前特斯拉 AI 总监，曾短暂回归 OpenAI，现已独立
- Dario Amodei: 2021 年离开联合创立 Anthropic
- Daniela Amodei: 2021 年离开联合创立 Anthropic'''
                }
            ],
            "sam altman": [
                {
                    'title': 'Sam Altman - OpenAI CEO',
                    'url': 'https://example.com/sam-altman',
                    'snippet': 'Sam Altman 是 OpenAI 的 CEO...',
                    'content': 'Sam Altman 目前是 OpenAI 的 CEO。他于 2023 年 11 月短暂离开公司，但在员工抗议后回归。他同时也因在 Y Combinator 的工作以及各种初创企业投资而闻名。'
                }
            ],
            "elon musk": [
                {
                    'title': 'Elon Musk 创立 xAI',
                    'url': 'https://example.com/elon-musk-ai',
                    'snippet': 'Elon Musk 于 2023 年创立 xAI...',
                    'content': 'Elon Musk 在 2015 年联合创立 OpenAI，但于 2018 年因与特斯拉 AI 发展的利益冲突离开董事会。2023 年，他创立了新的 AI 公司 xAI，专注于理解宇宙。他同时也是特斯拉、SpaceX 的 CEO 以及 X（前 Twitter）的所有者。'
                }
            ],
            "ilya sutskever": [
                {
                    'title': 'Ilya Sutskever 创立 Safe Superintelligence',
                    'url': 'https://example.com/ilya-sutskever',
                    'snippet': 'Ilya Sutskever 离开 OpenAI 创立 SSI...',
                    'content': 'Ilya Sutskever 曾任 OpenAI 首席科学家，在公司工作近十年后于 2024 年 5 月离开。他与 Daniel Gross 和 Daniel Levy 共同创立了 Safe Superintelligence Inc. (SSI)，专注于构建安全的 AGI。'
                }
            ]
        }

        # 查找匹配的模拟数据
        query_lower = query.lower()
        for key in mock_data:
            if key in query_lower:
                results = []
                for item in mock_data[key]:
                    results.append({
                        'title': item['title'],
                        'url': item['url'],
                        'snippet': item['snippet'],
                        'content': item['content'],
                        'content_length': len(item['content']),
                        'fetch_success': True
                    })

                return {
                    'query': query,
                    'num_results': len(results),
                    'results': results,
                    'timestamp': time.time(),
                    'mock': True
                }

        # 默认模拟结果
        return {
            'query': query,
            'num_results': 1,
            'results': [{
                'title': '模拟搜索结果',
                'url': 'https://example.com',
                'snippet': '这是用于测试的模拟搜索结果',
                'content': '无 API Key 可用时的模拟测试内容。',
                'content_length': 50,
                'fetch_success': True
            }],
            'timestamp': time.time(),
            'mock': True
        }

    def clear_cache(self):
        """清空页面缓存"""
        self.page_cache.clear()
        logger.info("页面缓存已清空")
