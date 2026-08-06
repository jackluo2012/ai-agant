# 工具参考指南

本 MCP 服务器提供的所有感知工具的完整参考。

## 目录

- [搜索工具 (3)](#搜索工具)
- [多模态理解工具 (4)](#多模态理解工具)
- [文件系统工具 (3)](#文件系统工具)
- [公共数据源工具 (6)](#公共数据源工具)
- [私有数据源工具 (2)](#私有数据源工具)

---

## 搜索工具

### 1. web_search

使用 DuckDuckGo 进行网络搜索（免费，无需 API 密钥）。

**参数：**
- `query` (字符串，必需): 搜索查询字符串
- `num_results` (整数，默认: 5): 返回结果数量（1-10）
- `region` (字符串，默认: "wt-wt"): 区域代码（cn-zh、us-en、wt-wt 全球）

**返回：**
```json
{
  "success": true,
  "message": {
    "query": "Python 编程",
    "results": [
      {
        "id": "ddg-0",
        "title": "Python 官方网站",
        "url": "https://www.python.org",
        "snippet": "Python 官方网站...",
        "source": "duckduckgo"
      }
    ],
    "count": 5
  },
  "metadata": {
    "query": "Python 编程",
    "search_engine": "duckduckgo",
    "total_results": 5,
    "search_time": 0.45
  }
}
```

**要求:** 无（免费 API）

---

### 2. download

从 URL 下载文件到本地存储。

**参数：**
- `url` (字符串，必需): 下载来源的 HTTP/HTTPS URL
- `output_path` (字符串，必需): 保存文件的本地路径
- `overwrite` (布尔，默认: false): 是否覆盖现有文件
- `timeout` (整数，默认: 180): 下载超时时间（秒）

**返回：**
```json
{
  "success": true,
  "message": "成功下载文件到 /path/to/file.pdf",
  "metadata": {
    "url": "https://example.com/file.pdf",
    "output_path": "/path/to/file.pdf",
    "file_size_bytes": 1048576,
    "duration_seconds": 2.3
  }
}
```

**限制:** 默认最大 100MB 文件大小

---

### 3. knowledge_base_search

搜索本地知识库目录中的相关文档。

**参数：**
- `query` (字符串，必需): 搜索查询
- `knowledge_base_path` (字符串，必需): 知识库目录路径
- `top_k` (整数，默认: 5): 返回的顶部结果数量

**返回：**
```json
{
  "success": true,
  "message": {
    "query": "机器学习",
    "results": [
      {
        "file": "docs/ml_basics.md",
        "snippet": "...机器学习算法...",
        "relevance": 12
      }
    ],
    "total_found": 3
  },
  "metadata": {
    "knowledge_base": "/path/to/kb",
    "top_k": 5
  }
}
```

**支持的文件类型:** .txt, .md, .json, .py, .js, .html

---

## 多模态理解工具

### 4. webpage_reader

从网页提取内容，包括文本和链接。

**参数：**
- `url` (字符串，必需): 网页 URL
- `extract_text` (布尔，默认: true): 是否提取主要文本内容
- `extract_links` (布尔，默认: false): 是否提取所有链接

**返回：**
```json
{
  "success": true,
  "message": {
    "url": "https://example.com",
    "title": "示例页面",
    "text": "页面内容...",
    "text_length": 10000,
    "links": []
  },
  "metadata": {
    "url": "https://example.com"
  }
}
```

---

### 5. document_reader

从文档中提取内容（PDF、DOCX、PPTX）。

**参数：**
- `file_path` (字符串，必需): 文档文件路径或 URL
- `extract_images` (布尔，默认: false): 是否提取图片

**返回：**
```json
{
  "success": true,
  "message": {
    "file_name": "document.pdf",
    "file_type": "pdf",
    "page_count": 10,
    "text": "文档内容...",
    "text_length": 15000
  },
  "metadata": {
    "file_path": "/path/to/document.pdf",
    "file_type": ".pdf"
  }
}
```

**支持的格式:** PDF, DOCX, PPTX

---

### 6. image_parser

解析和分析图片文件。

**参数：**
- `image_path` (字符串，必需): 图片文件路径或 URL
- `use_llm` (布尔，默认: true): 使用 LLM 进行图片理解

**返回：**
```json
{
  "success": true,
  "message": {
    "file_name": "image.jpg",
    "format": "JPEG",
    "mode": "RGB",
    "size": [1920, 1080],
    "width": 1920,
    "height": 1080,
    "note": "完整的 base64 数据可用于视觉 API 分析"
  },
  "metadata": {
    "file_path": "/path/to/image.jpg"
  }
}
```

**支持的格式:** JPG, PNG, GIF, BMP, TIFF, WEBP

---

### 7. video_parser

从视频文件提取元数据和信息。

**参数：**
- `video_path` (字符串，必需): 视频文件路径或 URL
- `extract_frames` (布尔，默认: false): 提取示例帧
- `frame_interval` (整数，默认: 30): 每隔 N 秒提取一帧

**返回：**
```json
{
  "success": true,
  "message": {
    "file_name": "video.mp4",
    "duration_seconds": 120.5,
    "fps": 30.0,
    "frame_count": 3615,
    "resolution": "1920x1080",
    "width": 1920,
    "height": 1080
  },
  "metadata": {
    "file_path": "/path/to/video.mp4"
  }
}
```

**支持的格式:** MP4, AVI, MOV, MKV, WEBM

---

## 文件系统工具

### 8. file_reader

读取文件并返回其内容。

**参数：**
- `file_path` (字符串，必需): 文件路径
- `encoding` (字符串，默认: "utf-8"): 文件编码
- `max_length` (整数，默认: 50000): 最大读取字符数

**返回：**
```json
{
  "success": true,
  "message": {
    "file_path": "/path/to/file.txt",
    "content": "文件内容...",
    "size_bytes": 1024,
    "truncated": false,
    "encoding": "utf-8"
  },
  "metadata": {
    "file_path": "/path/to/file.txt"
  }
}
```

---

### 9. grep

使用正则表达式在文件中搜索模式。

**参数：**
- `pattern` (字符串，必需): 搜索的正则表达式模式
- `directory` (字符串，必需): 搜索目录
- `file_pattern` (字符串，默认: "*"): 文件匹配模式（如：*.py）
- `recursive` (布尔，默认: true): 递归搜索
- `case_sensitive` (布尔，默认: false): 区分大小写搜索
- `max_results` (整数，默认: 100): 最大结果数

**返回：**
```json
{
  "success": true,
  "message": {
    "pattern": "def.*:",
    "results": [
      {
        "file": "src/main.py",
        "line_number": 42,
        "line": "def my_function():",
        "absolute_path": "/full/path/to/src/main.py"
      }
    ],
    "total_found": 15,
    "truncated": false
  },
  "metadata": {
    "directory": "/path/to/search",
    "file_pattern": "*.py",
    "recursive": true
  }
}
```

---

### 10. text_summarizer

对长文本内容进行摘要。

**参数：**
- `text` (字符串，必需): 待摘要的文本
- `max_length` (整数，默认: 500): 目标摘要长度（字符数）
- `use_llm` (布尔，默认: true): 使用 LLM 进行更好的摘要

**返回：**
```json
{
  "success": true,
  "message": {
    "original_length": 5000,
    "summary_length": 500,
    "summary": "摘要文本...",
    "method": "llm",
    "compression_ratio": 0.1
  },
  "metadata": {
    "method": "llm"
  }
}
```

**要求:** LLM API 配置（可选，如使用 LLM）

---

## 公共数据源工具

### 11. weather

获取位置的当前天气信息。

**参数：**
- `location` (字符串，必需): 城市名称
- `latitude` (浮点数，可选): 纬度坐标
- `longitude` (浮点数，可选): 经度坐标

**返回：**
```json
{
  "success": true,
  "message": {
    "location": "北京",
    "temperature": 25.5,
    "humidity": 60,
    "wind_speed": 3.5,
    "weather_description": "晴朗"
  },
  "metadata": {
    "location": "北京"
  }
}
```

**来源:** Open-Meteo（无需 API 密钥）

---

### 12. stock_price

获取当前股票价格和市场信息。

**参数：**
- `symbol` (字符串，必需): 股票代码（如：AAPL、TSLA）
- `interval` (字符串，默认: "1d"): 数据间隔

**返回：**
```json
{
  "success": true,
  "message": {
    "symbol": "AAPL",
    "currency": "USD",
    "current_price": 175.43,
    "previous_close": 174.20,
    "day_high": 176.00,
    "day_low": 173.80,
    "volume": 52341000
  },
  "metadata": {
    "symbol": "AAPL"
  }
}
```

**来源:** Yahoo Finance（无需 API 密钥）

---

### 13. currency_converter

在不同货币之间进行转换。

**参数：**
- `amount` (浮点数，必需): 转换金额
- `from_currency` (字符串，必需): 源货币代码（如：USD）
- `to_currency` (字符串，必需): 目标货币代码（如：CNY）

**返回：**
```json
{
  "success": true,
  "message": {
    "amount": 100.0,
    "from_currency": "USD",
    "to_currency": "CNY",
    "exchange_rate": 7.2,
    "converted_amount": 720.0,
    "timestamp": "2024-01-15"
  },
  "metadata": {
    "rate": 7.2
  }
}
```

**来源:** Exchange Rate API（无需 API 密钥）

---

### 14. wikipedia_search

搜索 Wikipedia 并检索文章摘要。

**参数：**
- `query` (字符串，必需): 搜索查询
- `language` (字符串，默认: "zh"): Wikipedia 语言（zh 中文、en 英文等）
- `sentences` (整数，默认: 5): 摘要句子数量

**返回：**
```json
{
  "success": true,
  "message": {
    "title": "人工智能",
    "url": "https://zh.wikipedia.org/wiki/人工智能",
    "summary": "人工智能（AI）是...",
    "language": "zh"
  },
  "metadata": {
    "query": "人工智能",
    "language": "zh"
  }
}
```

**来源:** Wikipedia API（无需 API 密钥）

---

### 15. arxiv_search

在 ArXiv 上搜索学术论文。

**参数：**
- `query` (字符串，必需): 搜索查询
- `max_results` (整数，默认: 5): 最大论文数量
- `sort_by` (字符串，默认: "relevance"): 排序方式

**返回：**
```json
{
  "success": true,
  "message": {
    "query": "machine learning",
    "papers": [
      {
        "title": "深度学习论文",
        "authors": ["张三", "李四"],
        "summary": "论文摘要...",
        "published": "2024-01-15T00:00:00",
        "url": "https://arxiv.org/abs/2401.12345",
        "pdf_url": "https://arxiv.org/pdf/2401.12345"
      }
    ],
    "count": 5
  },
  "metadata": {
    "query": "machine learning",
    "max_results": 5
  }
}
```

**来源:** ArXiv API（无需 API 密钥）

---

### 16. wayback_search

搜索 Wayback Machine 的网页存档版本。

**参数：**
- `url` (字符串，必需): 搜索的 URL
- `year` (整数，可选): 按特定年份过滤
- `limit` (整数，默认: 10): 最大快照数量

**返回：**
```json
{
  "success": true,
  "message": {
    "url": "https://example.com",
    "snapshots": [
      {
        "timestamp": "2024-01-15T10:30:00",
        "url": "https://web.archive.org/web/20240115103000/https://example.com",
        "status_code": "200"
      }
    ],
    "count": 10
  },
  "metadata": {
    "url": "https://example.com",
    "year": null
  }
}
```

**来源:** Internet Archive（无需 API 密钥）

---

## 私有数据源工具

### 17. calendar_events

从 Google Calendar 获取事件。

**参数：**
- `start_date` (字符串，可选): 开始日期（ISO 格式，默认今天）
- `end_date` (字符串，可选): 结束日期（ISO 格式，默认 7 天后）
- `calendar_id` (字符串，默认: "primary"): 日历 ID
- `max_results` (整数，默认: 10): 最大事件数量

**返回：**
```json
{
  "success": true,
  "message": {
    "events": [
      {
        "id": "event_id_123",
        "summary": "团队会议",
        "start": "2024-01-15T10:00:00Z",
        "end": "2024-01-15T11:00:00Z",
        "location": "会议室 A"
      }
    ],
    "count": 5
  },
  "metadata": {
    "start_date": "2024-01-15T00:00:00Z",
    "end_date": "2024-01-22T00:00:00Z"
  }
}
```

**要求:** Google Calendar API OAuth2 认证

---

### 18. notion_search

搜索 Notion 工作区或特定数据库。

**参数：**
- `query` (字符串，必需): 搜索查询
- `database_id` (字符串，可选): 搜索的特定数据库 ID
- `page_size` (整数，默认: 10): 每页结果数

**返回：**
```json
{
  "success": true,
  "message": {
    "query": "项目笔记",
    "results": [
      {
        "id": "page_id_123",
        "type": "page",
        "url": "https://notion.so/page_id_123",
        "title": "项目规划",
        "created_time": "2024-01-15T10:00:00Z",
        "last_edited_time": "2024-01-16T14:30:00Z"
      }
    ],
    "count": 3
  },
  "metadata": {
    "database_id": null
  }
}
```

**要求:** Notion API 密钥

---

## 错误响应格式

所有工具以标准化格式返回错误：

```json
{
  "success": false,
  "message": "错误描述",
  "metadata": {
    "error_type": "specific_error_type"
  }
}
```

常见错误类型：
- `missing_credentials`: API 密钥未配置
- `api_request_failed`: 外部 API 请求失败
- `file_not_found`: 指定的文件不存在
- `invalid_parameters`: 无效的输入参数
- `timeout`: 操作超时
- `permission_denied`: 权限不足

---

## 免费工具（无需 API 密钥）

以下工具完全免费，无需任何配置：

| 工具 | API 来源 |
|------|----------|
| web_search | DuckDuckGo |
| weather | Open-Meteo |
| stock_price | Yahoo Finance |
| currency_converter | ExchangeRate-API |
| wikipedia_search | Wikipedia |
| arxiv_search | ArXiv |
| wayback_search | Internet Archive |
| knowledge_base_search | 本地文件 |
| webpage_reader | 网页抓取 |
| file_reader | 本地文件 |
| grep | 本地文件 |

这些工具可以立即使用，无需任何设置！
