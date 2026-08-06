"""
感知工具 MCP 服务器主入口

该 MCP 服务器提供全面的感知能力，包括：
- 搜索工具（网络搜索、知识库、文件下载）
- 多模态理解（网页、文档、图片、视频）
- 文件系统操作（读取、grep、摘要）
- 公开数据源（天气、股票、货币、Wikipedia、ArXiv、Wayback）
- 私有数据源（Google 日历、Notion）
"""
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from mcp.server import FastMCP
from pydantic import Field

# 添加项目根目录到路径，用于导入统一 LLM 客户端
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 导入所有工具函数
from search_tools import search_web, download_file, search_knowledge_base
from multimodal_tools import (
    read_webpage, read_document, parse_image, parse_video,
    extract_youtube_transcript, download_youtube_video
)
from filesystem_tools import read_file, grep_search, summarize_text
from public_data_tools import (
    get_weather, get_stock_price, convert_currency,
    search_wikipedia, search_arxiv, search_wayback,
    get_crypto_price, search_location, search_poi
)
from private_data_tools import get_calendar_events, search_notion
from pubchem_tools import (
    search_compounds, get_compound_properties,
    get_compound_synonyms, search_similar_compounds
)
from yahoo_finance_tools import (
    get_stock_quote, get_historical_data,
    get_company_info, get_financial_statements
)
from document_processing_tools import (
    extract_pdf_text, extract_docx_content,
    extract_pptx_content, extract_csv_content
)
from media_processing_tools import (
    transcribe_audio_whisper, extract_audio_metadata,
    extract_text_ocr, analyze_image_ai,
    extract_video_keyframes, analyze_video_ai,
    trim_audio, get_image_metadata
)
from google_search_enhanced import google_search_api, read_webpage_content
from wiki_enhanced import (
    get_article_content, get_article_categories,
    get_article_links, get_article_history
)
from arxiv_enhanced import get_paper_details, download_paper, get_arxiv_categories
from wayback_enhanced import get_archived_content


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

load_dotenv()

# 初始化 MCP 服务器
mcp = FastMCP(
    "perception-tools",
    instructions="""
感知工具 MCP 服务器

提供各种感知和数据检索功能的全面 MCP 服务器：

## 🔍 搜索工具
- 使用 DuckDuckGo 进行网络搜索（免费，无需 API 密钥）
- 本地知识库搜索
- 从 URL 下载文件

## 🌐 多模态理解
- 网页内容提取
- 文档阅读（PDF、DOCX、PPTX）
- 图片解析和分析
- 视频元数据提取

## 📁 文件系统工具
- 支持多种编码的文件读取
- 类 grep 的模式搜索
- 智能文本摘要（支持 LLM）

## 📊 公开数据源
- 天气信息
- 股票价格和市场数据
- 加密货币价格（CoinGecko）
- 货币转换
- 位置搜索 / 地理编码（Nominatim）
- 兴趣点搜索（Overpass）
- Wikipedia 搜索
- ArXiv 学术论文
- Wayback Machine 存档

## 🔐 私有数据源
- Google 日历事件
- Notion 工作区搜索

## 🎬 媒体处理
- 音频转录（Whisper）
- 图片 OCR 识别
- AI 视觉分析
- 视频关键帧提取

所有工具支持中文提示词和响应。
"""
)


# ============================================================================
# 🔍 搜索工具
# ============================================================================

@mcp.tool(description="使用 DuckDuckGo 进行网络搜索（免费，无需 API 密钥）")
async def web_search(
    query: str = Field(description="搜索查询字符串"),
    num_results: int = Field(default=5, description="结果数量（1-10）"),
    region: str = Field(default="wt-wt", description="区域代码（例如：'cn-zh'、'us-en'、'wt-wt' 表示全球）")
):
    """搜索网络并返回结果。"""
    return await search_web(query, num_results, region)


@mcp.tool(description="从 URL 下载文件到本地存储")
async def download(
    url: str = Field(description="下载来源 URL"),
    output_path: str = Field(description="保存文件的本地路径"),
    overwrite: bool = Field(default=False, description="覆盖现有文件"),
    timeout: int = Field(default=180, description="下载超时时间（秒）")
):
    """从 URL 下载文件。"""
    return await download_file(url, output_path, overwrite, timeout)


@mcp.tool(description="搜索本地知识库目录")
async def knowledge_base_search(
    query: str = Field(description="搜索查询"),
    knowledge_base_path: str = Field(description="知识库目录路径"),
    top_k: int = Field(default=5, description="返回结果数量")
):
    """搜索本地知识库。"""
    return await search_knowledge_base(query, knowledge_base_path, top_k)


# ============================================================================
# 🌐 多模态理解工具
# ============================================================================

@mcp.tool(description="读取并从网页提取内容")
async def webpage_reader(
    url: str = Field(description="网页 URL"),
    extract_text: bool = Field(default=True, description="提取文本内容"),
    extract_links: bool = Field(default=False, description="提取链接")
):
    """读取网页内容。"""
    return await read_webpage(url, extract_text, extract_links)


@mcp.tool(description="读取并从文档中提取内容（PDF、DOCX、PPTX）")
async def document_reader(
    file_path: str = Field(description="文档文件路径或 URL"),
    extract_images: bool = Field(default=False, description="提取图片")
):
    """读取文档内容。"""
    return await read_document(file_path, extract_images)


@mcp.tool(description="解析和分析图片文件")
async def image_parser(
    image_path: str = Field(description="图片文件路径或 URL"),
    use_llm: bool = Field(default=True, description="使用 LLM 进行分析")
):
    """解析图片内容。"""
    return await parse_image(image_path, use_llm)


@mcp.tool(description="解析并从视频文件提取元数据")
async def video_parser(
    video_path: str = Field(description="视频文件路径或 URL"),
    extract_frames: bool = Field(default=False, description="提取示例帧"),
    frame_interval: int = Field(default=30, description="帧提取间隔")
):
    """解析视频元数据。"""
    return await parse_video(video_path, extract_frames, frame_interval)


# ============================================================================
# 📁 文件系统工具
# ============================================================================

@mcp.tool(description="读取文件并返回其内容")
async def file_reader(
    file_path: str = Field(description="文件路径"),
    encoding: str = Field(default="utf-8", description="文件编码"),
    max_length: int = Field(default=50000, description="最大读取字符数")
):
    """读取文件内容。"""
    return await read_file(file_path, encoding, max_length)


@mcp.tool(description="在文件中搜索模式（类 grep 功能）")
async def grep(
    pattern: str = Field(description="正则表达式模式"),
    directory: str = Field(description="搜索目录"),
    file_pattern: str = Field(default="*", description="文件模式（例如：*.py）"),
    recursive: bool = Field(default=True, description="递归搜索"),
    case_sensitive: bool = Field(default=False, description="区分大小写搜索"),
    max_results: int = Field(default=100, description="最大结果数")
):
    """在文件中搜索模式。"""
    return await grep_search(pattern, directory, file_pattern, recursive, case_sensitive, max_results)


@mcp.tool(description="对长文本内容进行智能摘要（支持 LLM）")
async def text_summarizer(
    text: str = Field(description="待摘要的文本"),
    max_length: int = Field(default=500, description="目标摘要长度"),
    use_llm: bool = Field(default=True, description="使用 LLM 进行摘要")
):
    """对文本进行摘要。"""
    return await summarize_text(text, max_length, use_llm)


# ============================================================================
# 📊 公开数据源工具
# ============================================================================

@mcp.tool(description="获取位置的当前天气信息（Open-Meteo，免费，无需 API 密钥）")
async def weather(
    location: str = Field(description="城市名称（自动地理编码）"),
    latitude: float | None = Field(default=None, description="纬度坐标（可选）"),
    longitude: float | None = Field(default=None, description="经度坐标（可选）")
):
    """获取天气数据。"""
    return await get_weather(location, latitude, longitude)


@mcp.tool(description="获取股票价格和市场信息")
async def stock_price(
    symbol: str = Field(description="股票代码（例如：AAPL）"),
    interval: str = Field(default="1d", description="数据间隔")
):
    """获取股票价格。"""
    return await get_stock_price(symbol, interval)


@mcp.tool(description="货币之间转换")
async def currency_converter(
    amount: float = Field(description="转换金额"),
    from_currency: str = Field(description="源货币代码（例如：USD）"),
    to_currency: str = Field(description="目标货币代码（例如：CNY）")
):
    """转换货币。"""
    return await convert_currency(amount, from_currency, to_currency)


@mcp.tool(description="获取加密货币价格信息（CoinGecko，免费，无需 API 密钥）")
async def crypto_price(
    symbol: str = Field(description="加密货币符号或 ID（例如：bitcoin、ethereum、btc、eth）"),
    vs_currency: str = Field(default="usd", description="目标货币（usd、cny、eur 等）")
):
    """获取加密货币价格。"""
    return await get_crypto_price(symbol, vs_currency)


@mcp.tool(description="使用 Nominatim/OpenStreetMap 搜索位置（免费，无需 API 密钥）")
async def location_search(
    query: str = Field(description="位置查询（例如：'埃菲尔铁塔'、'北京'、'东京'）"),
    limit: int = Field(default=5, description="最大结果数（1-50）"),
    country_code: str | None = Field(default=None, description="国家代码过滤器（例如：'cn'、'us'、'jp'）")
):
    """搜索位置（地理编码）。"""
    return await search_location(query, limit, country_code)


@mcp.tool(description="使用 Overpass/OpenStreetMap 搜索位置附近的兴趣点（免费，无需 API 密钥）")
async def poi_search(
    query: str = Field(description="兴趣点类型（例如：'restaurant'、'cafe'、'hospital'、'atm'、'hotel'）"),
    latitude: float = Field(description="中心纬度坐标"),
    longitude: float = Field(description="中心经度坐标"),
    radius: int = Field(default=1000, description="搜索半径（米）"),
    limit: int = Field(default=10, description="最大结果数")
):
    """搜索兴趣点。"""
    return await search_poi(query, latitude, longitude, radius, limit)


@mcp.tool(description="搜索 Wikipedia 并获取文章摘要")
async def wikipedia_search(
    query: str = Field(description="搜索查询"),
    language: str = Field(default="zh", description="Wikipedia 语言（zh=中文、en=英文）"),
    sentences: int = Field(default=5, description="摘要句子数")
):
    """搜索 Wikipedia。"""
    return await search_wikipedia(query, language, sentences)


@mcp.tool(description="搜索 ArXiv 学术论文")
async def arxiv_search(
    query: str = Field(description="搜索查询"),
    max_results: int = Field(default=5, description="最大结果数"),
    sort_by: str = Field(default="relevance", description="排序方式")
):
    """搜索 ArXiv。"""
    return await search_arxiv(query, max_results, sort_by)


@mcp.tool(description="搜索 Wayback Machine 的存档网页")
async def wayback_search(
    url: str = Field(description="搜索的 URL"),
    year: int | None = Field(default=None, description="按年份过滤"),
    limit: int = Field(default=10, description="最大快照数")
):
    """搜索 Wayback Machine。"""
    return await search_wayback(url, year, limit)


# ============================================================================
# 📺 YouTube 工具
# ============================================================================

@mcp.tool(description="从 YouTube 视频提取字幕")
async def youtube_transcript(
    video_id: str = Field(description="YouTube 视频 ID 或 URL"),
    language_code: str = Field(default="zh", description="字幕语言代码"),
    translate_to_language: str | None = Field(default=None, description="翻译到此语言")
):
    """提取 YouTube 字幕。"""
    return await extract_youtube_transcript(video_id, language_code, translate_to_language)


@mcp.tool(description="下载 YouTube 视频")
async def youtube_download(
    url: str = Field(description="YouTube 视频 URL"),
    output_dir: str = Field(default=".", description="输出目录"),
    max_resolution: str = Field(default="720p", description="最大分辨率")
):
    """下载 YouTube 视频。"""
    return await download_youtube_video(url, output_dir, max_resolution)


# ============================================================================
# 🔬 PubChem 化学数据工具
# ============================================================================

@mcp.tool(description="在 PubChem 中搜索化合物")
async def pubchem_search(
    query: str = Field(description="搜索词或标识符"),
    search_type: str = Field(default="name", description="类型：name、cid、smiles、inchi、formula"),
    max_results: int = Field(default=10, description="最大结果数（1-100）")
):
    """搜索 PubChem 化合物。"""
    return await search_compounds(query, search_type, max_results)


@mcp.tool(description="获取 PubChem 化合物的详细属性")
async def pubchem_properties(
    cid: int = Field(description="PubChem 化合物 ID"),
    properties: list[str] | None = Field(default=None, description="属性名称列表")
):
    """获取化合物属性。"""
    return await get_compound_properties(cid, properties)


@mcp.tool(description="获取 PubChem 化合物的同义词")
async def pubchem_synonyms(
    cid: int = Field(description="PubChem 化合物 ID"),
    max_synonyms: int = Field(default=20, description="最大同义词数（1-100）")
):
    """获取化合物同义词。"""
    return await get_compound_synonyms(cid, max_synonyms)


@mcp.tool(description="在 PubChem 中搜索结构相似的化合物")
async def pubchem_similar(
    cid: int = Field(description="参考化合物 CID"),
    similarity_threshold: float = Field(default=0.9, description="相似度阈值（0.0-1.0）"),
    max_results: int = Field(default=10, description="最大结果数（1-50）")
):
    """搜索相似化合物。"""
    return await search_similar_compounds(cid, similarity_threshold, max_results)


# ============================================================================
# 📈 Yahoo Finance 工具
# ============================================================================

@mcp.tool(description="获取当前股票报价和市场数据")
async def yfinance_quote(
    symbol: str = Field(description="股票代码（例如：AAPL、MSFT）")
):
    """获取股票报价。"""
    return await get_stock_quote(symbol)


@mcp.tool(description="获取历史股票价格数据")
async def yfinance_historical(
    symbol: str = Field(description="股票代码"),
    start: str = Field(description="开始日期（YYYY-MM-DD）"),
    end: str = Field(description="结束日期（YYYY-MM-DD）"),
    interval: str = Field(default="1d", description="数据间隔（1d、1wk、1mo）"),
    max_rows_preview: int = Field(default=10, description="预览最大行数")
):
    """获取历史股票数据。"""
    return await get_historical_data(symbol, start, end, interval, max_rows_preview)


@mcp.tool(description="获取全面的公司信息")
async def yfinance_company_info(
    symbol: str = Field(description="股票代码")
):
    """获取公司信息。"""
    return await get_company_info(symbol)


@mcp.tool(description="获取财务报表（利润表、资产负债表、现金流量表）")
async def yfinance_financials(
    symbol: str = Field(description="股票代码"),
    statement_type: str = Field(description="类型：income_statement、balance_sheet、cash_flow"),
    period_type: str = Field(default="annual", description="周期：annual 或 quarterly"),
    max_columns_preview: int = Field(default=4, description="最大显示周期数")
):
    """获取财务报表。"""
    return await get_financial_statements(symbol, statement_type, period_type, max_columns_preview)


# ============================================================================
# 📄 文档处理工具
# ============================================================================

@mcp.tool(description="从 PDF 文件提取文本，支持可选的页码范围")
async def pdf_extract(
    file_path: str = Field(description="PDF 文件路径"),
    page_range: str | None = Field(default=None, description="页码范围（例如：'1-5' 或 '1,3,5'）")
):
    """从 PDF 提取文本。"""
    return await extract_pdf_text(file_path, page_range)


@mcp.tool(description="从 Word 文档提取内容（DOCX）")
async def docx_extract(
    file_path: str = Field(description="DOCX 文件路径")
):
    """从 DOCX 提取内容。"""
    return await extract_docx_content(file_path)


@mcp.tool(description="从 PowerPoint 演示文稿提取内容（PPTX）")
async def pptx_extract(
    file_path: str = Field(description="PPTX 文件路径")
):
    """从 PPTX 提取内容。"""
    return await extract_pptx_content(file_path)


@mcp.tool(description="提取并解析 CSV 文件数据")
async def csv_parse(
    file_path: str = Field(description="CSV 文件路径"),
    max_rows: int = Field(default=1000, description="最大读取行数")
):
    """解析 CSV 数据。"""
    return await extract_csv_content(file_path, max_rows)


# ============================================================================
# 🎬 媒体处理工具
# ============================================================================

@mcp.tool(description="使用 Whisper 将音频转写为文本")
async def audio_transcribe(
    file_path: str = Field(description="音频文件路径"),
    model_size: str = Field(default="base", description="Whisper 模型大小"),
    language: str = Field(default="zh", description="语言代码")
):
    """将音频转写为文本。"""
    return await transcribe_audio_whisper(file_path, model_size, language)


@mcp.tool(description="提取音频文件元数据")
async def audio_metadata(
    file_path: str = Field(description="音频文件路径")
):
    """提取音频元数据。"""
    return await extract_audio_metadata(file_path)


@mcp.tool(description="使用 OCR 从图片提取文本")
async def image_ocr(
    image_path: str = Field(description="图片文件路径"),
    language: str = Field(default="chi_sim+eng", description="OCR 语言")
):
    """使用 OCR 从图片提取文本。"""
    return await extract_text_ocr(image_path, language)


@mcp.tool(description="使用 AI 视觉分析图片")
async def image_analyze(
    image_path: str = Field(description="图片文件路径"),
    prompt: str = Field(default="请详细描述这张图片的内容", description="分析提示词")
):
    """使用 AI 分析图片。"""
    return await analyze_image_ai(image_path, prompt)


@mcp.tool(description="从视频提取关键帧")
async def video_keyframes(
    video_path: str = Field(description="视频文件路径"),
    num_frames: int = Field(default=10, description="提取的关键帧数量")
):
    """提取视频关键帧。"""
    return await extract_video_keyframes(video_path, num_frames)


@mcp.tool(description="使用 AI 视觉分析视频内容")
async def video_analyze(
    video_path: str = Field(description="视频文件路径"),
    num_frames: int = Field(default=5, description="分析的帧数"),
    prompt: str = Field(default="分析此视频并描述其中发生的事情", description="分析提示词")
):
    """使用 AI 分析视频。"""
    return await analyze_video_ai(video_path, num_frames, prompt)


@mcp.tool(description="将音频文件裁剪到指定时间范围")
async def audio_trim(
    audio_path: str = Field(description="音频文件路径"),
    start_time: float = Field(description="开始时间（秒）"),
    duration: float | None = Field(default=None, description="持续时间（秒）"),
    output_path: str | None = Field(default=None, description="输出文件路径")
):
    """裁剪音频文件。"""
    return await trim_audio(audio_path, start_time, duration, output_path)


@mcp.tool(description="获取详细图片元数据，包括 EXIF")
async def image_metadata(
    image_path: str = Field(description="图片文件路径")
):
    """获取图片元数据。"""
    return await get_image_metadata(image_path)


# ============================================================================
# 🔍 Google 搜索增强工具
# ============================================================================

@mcp.tool(description="使用 API 或 DuckDuckGo 回退进行 Google 搜索")
async def google_search_enhanced(
    query: str = Field(description="搜索查询"),
    num_results: int = Field(default=5, description="结果数量（1-10）"),
    safe_search: bool = Field(default=True, description="启用安全搜索"),
    language: str = Field(default="zh", description="语言代码"),
    country: str = Field(default="cn", description="国家代码")
):
    """增强的 Google 搜索。"""
    return await google_search_api(query, num_results, safe_search, language, country)


@mcp.tool(description="读取并从网页提取内容（增强版）")
async def webpage_read_enhanced(
    url: str = Field(description="读取的 URL"),
    extract_links: bool = Field(default=False, description="从页面提取链接")
):
    """读取网页内容。"""
    return await read_webpage_content(url, extract_links)


# ============================================================================
# 📚 Wikipedia 增强工具
# ============================================================================

@mcp.tool(description="获取完整的 Wikipedia 文章内容")
async def wiki_article_full(
    title: str = Field(description="文章标题"),
    language: str = Field(default="zh", description="语言代码")
):
    """获取完整的 Wikipedia 文章。"""
    return await get_article_content(title, language)


@mcp.tool(description="获取 Wikipedia 文章分类")
async def wiki_article_categories(
    title: str = Field(description="文章标题"),
    language: str = Field(default="zh", description="语言代码")
):
    """获取文章分类。"""
    return await get_article_categories(title, language)


@mcp.tool(description="从 Wikipedia 文章获取链接")
async def wiki_article_links(
    title: str = Field(description="文章标题"),
    language: str = Field(default="zh", description="语言代码")
):
    """获取文章链接。"""
    return await get_article_links(title, language)


@mcp.tool(description="获取 Wikipedia 文章的历史版本")
async def wiki_article_history(
    title: str = Field(description="文章标题"),
    date: str = Field(description="日期（YYYY/MM/DD）"),
    language: str = Field(default="zh", description="语言代码")
):
    """获取历史 Wikipedia 文章。"""
    return await get_article_history(title, date, language)


# ============================================================================
# 📄 ArXiv 增强工具
# ============================================================================

@mcp.tool(description="获取详细的 ArXiv 论文信息")
async def arxiv_paper_details(
    paper_id: str = Field(description="ArXiv 论文 ID")
):
    """获取论文详情。"""
    return await get_paper_details(paper_id)


@mcp.tool(description="下载 ArXiv 论文 PDF")
async def arxiv_download(
    paper_id: str = Field(description="ArXiv 论文 ID"),
    download_dir: str = Field(default=".", description="下载目录")
):
    """下载 ArXiv 论文。"""
    return await download_paper(paper_id, download_dir)


@mcp.tool(description="获取 ArXiv 主题分类")
async def arxiv_categories():
    """获取 ArXiv 分类。"""
    return await get_arxiv_categories()


# ============================================================================
# 📜 Wayback 增强工具
# ============================================================================

@mcp.tool(description="从存档网页获取内容")
async def wayback_archived_content(
    url: str = Field(description="检索的 URL"),
    timestamp: str = Field(description="时间戳（YYYYMMDDhhmmss）")
):
    """获取存档网页内容。"""
    return await get_archived_content(url, timestamp)


# ============================================================================
# 🔐 私有数据源工具
# ============================================================================

@mcp.tool(description="从 Google 日历获取事件")
async def calendar_events(
    start_date: str | None = Field(default=None, description="开始日期（ISO 格式）"),
    end_date: str | None = Field(default=None, description="结束日期（ISO 格式）"),
    calendar_id: str = Field(default="primary", description="日历 ID"),
    max_results: int = Field(default=10, description="最大事件数")
):
    """获取日历事件。"""
    return await get_calendar_events(start_date, end_date, calendar_id, max_results)


@mcp.tool(description="搜索 Notion 工作区")
async def notion_search(
    query: str = Field(description="搜索查询"),
    database_id: str | None = Field(default=None, description="特定数据库 ID"),
    page_size: int = Field(default=10, description="每页结果数")
):
    """搜索 Notion。"""
    return await search_notion(query, database_id, page_size)


# ============================================================================
# 🚀 运行服务器
# ============================================================================

if __name__ == "__main__":
    logging.info("启动感知工具 MCP 服务器！")
    mcp.run(transport="stdio")
