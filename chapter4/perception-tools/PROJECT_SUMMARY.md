# 感知工具 MCP 服务器 - 项目摘要

## 概述

一个全面的 MCP（模型上下文协议）服务器，实现了 40+ 个感知工具，组织为 9 个类别，遵循 SOLID 原则和模块化架构。

## 实现细节

### 架构

项目遵循**单一职责原则**，每个工具类别使用独立模块：

```
perception-tools/
├── src/
│   ├── base.py                  # 共享模型和工具
│   ├── search_tools.py          # 搜索功能（3 个工具）
│   ├── multimodal_tools.py      # 多模态理解（6 个工具）
│   ├── filesystem_tools.py      # 文件操作（3 个工具）
│   ├── media_processing_tools.py # 媒体处理（9 个工具）
│   ├── public_data_tools.py     # 公共 API（9 个工具）
│   ├── private_data_tools.py    # 私有数据源（2 个工具）
│   ├── document_processing_tools.py # 文档处理（4 个工具）
│   ├── pubchem_tools.py         # 化学数据（3 个工具）
│   ├── yahoo_finance_tools.py  # 金融数据（4 个工具）
│   ├── google_search_enhanced.py # Google 搜索（2 个工具）
│   ├── wiki_enhanced.py         # Wikipedia 增强（4 个工具）
│   ├── arxiv_enhanced.py        # ArXiv 增强（3 个工具）
│   ├── wayback_enhanced.py      # Wayback 增强（1 个工具）
│   └── main.py                  # MCP 服务器入口
├── requirements.txt             # 依赖
├── README.md                    # 用户文档
├── SETUP.md                     # 安装说明
├── QUICK_START.md               # 快速开始
├── TOOL_REFERENCE.md            # 完整 API 参考
├── ARCHITECTURE.md              # 系统架构
├── CHANGES.md                   # 更新日志
├── INDEX.md                     # 导航索引
└── PROJECT_SUMMARY.md           # 本文件
```

### 应用的设计原则

#### KISS（简单至上）
- 每个工具有单一、明确的目的
- 简单的异步函数签名
- 直观的错误处理

#### DRY（杜绝重复）
- `base.py` 中的公共工具（ActionResponse、文件验证、URL 下载）
- 共享的错误处理模式
- 可复用的 Pydantic 模型

#### SOLID 原则

**单一职责：**
- 每个模块处理一类工具
- 基础模块仅提供共享功能
- 工具具有单一、明确定义的目的

**开闭原则：**
- 无需修改现有代码即可添加新工具
- 通过新模块扩展
- MCP 装饰器模式允许非侵入式工具注册

**里氏替换：**
- 所有工具返回一致的 `ActionResponse` 格式
- 所有工具具有统一的错误处理

**接口隔离：**
- 工具仅暴露必要参数
- 具有合理默认值的可选参数
- 不强制依赖未使用的功能

**依赖倒置：**
- 工具依赖抽象（ActionResponse、TextContent）
- 通过接口访问外部服务
- 通过环境变量配置

## 工具类别

### 1. 搜索工具（3 个工具）
- `web_search`: DuckDuckGo 网络搜索（免费，无需 API）
- `download`: HTTP/HTTPS 文件下载，带安全检查
- `knowledge_base_search`: 本地文档搜索

### 2. 多模态理解工具（6 个工具）
- `webpage_reader`: HTML 内容提取
- `document_reader`: PDF/DOCX/PPTX 处理
- `image_parser`: 使用 PIL 进行图片分析
- `video_parser`: 使用 OpenCV 提取视频元数据
- `youtube_transcript`: YouTube 字幕提取
- `youtube_download`: YouTube 视频下载

### 3. 文件系统工具（3 个工具）
- `file_reader`: 支持多种编码的文件读取
- `grep`: 文件中的正则表达式模式搜索
- `text_summarizer`: 文本摘要（抽取式/LLM）

### 4. 公共数据源工具（9 个工具）
- `weather`: Open-Meteo 天气 API（免费）
- `stock_price`: Yahoo Finance 数据（免费）
- `currency_converter`: 汇率转换（免费）
- `crypto_price`: CoinGecko 加密货币（免费）
- `wikipedia_search`: Wikipedia API
- `arxiv_search`: ArXiv 学术论文搜索
- `wayback_search`: Internet Archive 访问
- `location_search`: OpenStreetMap 位置搜索
- `poi_search`: OpenStreetMap 兴趣点搜索

### 5. 媒体处理工具（9 个工具）
- `audio_transcribe`: Whisper 音频转录
- `audio_metadata`: 音频元数据提取
- `image_ocr`: 图片 OCR 文字识别
- `image_analyze`: AI 图片分析
- `video_keyframes`: 视频关键帧提取
- `video_analyze`: AI 视频分析
- `audio_trim`: 音频裁剪
- `image_metadata`: 图片元数据

### 6. 科学数据工具（3 个工具）
- `pubchem_search`: PubChem 化合物搜索
- `pubchem_properties`: 化合物属性
- `pubchem_synonyms`: 化合物同义词

### 7. 金融数据工具（4 个工具）
- `yfinance_quote`: 股票报价
- `yfinance_historical`: 历史数据
- `yfinance_company_info`: 公司信息
- `yfinance_financials`: 财务报表

### 8. 文档处理工具（4 个工具）
- `pdf_extract`: PDF 文本提取
- `docx_extract`: DOCX 内容提取
- `pptx_extract`: PPTX 内容提取
- `csv_parse`: CSV 数据解析

### 9. 私有数据源工具（2 个工具）
- `calendar_events`: Google Calendar OAuth2 集成
- `notion_search`: Notion API

## 关键特性

### 错误处理
- 一致的错误响应格式
- 详细的错误类型用于调试
- 服务不可用时优雅降级

### 配置管理
- 基于环境变量的配置
- 模板文件便于设置
- 明确标记可选依赖

### 响应格式
所有工具返回标准化的 JSON 响应：

```json
{
  "success": true/false,
  "message": "结果数据或错误消息",
  "metadata": {
    "additional": "上下文信息"
  }
}
```

### 安全特性
- 下载的文件大小限制
- 网络操作的超时控制
- 路径验证防止目录遍历
- 外部请求的 URL 验证

### 中文化支持
- 所有用户可见提示词使用中文
- 完整的中文注释和文档
- 工具描述使用中文

### 统一 LLM 客户端
- 使用项目统一的 LLM 配置
- 支持多种 LLM 提供商
- 自动回退机制

## 测试

### 导入验证
```bash
python test_imports.py
```

### 功能测试
```bash
python quickstart.py
```

### 新工具测试
```bash
python test_new_tools.py
```

### 手动 MCP 服务器测试
```bash
cd src && python main.py
```

## 依赖

### 核心
- `mcp`: MCP 服务器框架（项目根目录提供）
- `pydantic`: 数据验证（项目根目录提供）
- `python-dotenv`: 配置管理（项目根目录提供）
- `requests`: HTTP 客户端
- `openai`: LLM 客户端（项目根目录提供）

### 文档处理
- `PyPDF2`: PDF 解析
- `python-docx`: Word 文档
- `python-pptx`: PowerPoint 演示文稿
- `Pillow`: 图片处理
- `opencv-python`: 视频处理

### 网页抓取
- `beautifulsoup4`: HTML 解析
- `lxml`: XML/HTML 解析器

### 数据源
- `wikipedia`: Wikipedia API
- `arxiv`: ArXiv API
- `yfinance`: Yahoo Finance
- `pubchempy`: PubChem 数据

### 可选
- Google Calendar: `google-auth-*`, `google-api-python-client`
- Notion: `notion-client`
- `openai-whisper`: 本地 Whisper 模型
- `pytesseract`: OCR 功能

## 配置要求

### AI 功能需要
- `API_KEY`: LLM API 密钥
- `LLM_PROVIDER`: LLM 提供商
- `LLM_MODEL`: 模型名称
- `BASE_URL`: API 基础 URL（某些提供商）

### 可选
- `NOTION_API_KEY`: Notion 集成
- Google OAuth2 凭证: Calendar 集成

## 性能考虑

- 默认超时: 30-180 秒（取决于操作）
- 文件大小限制: 下载 100MB，视频 500MB
- 文本截断: 文件读取 50,000 字符
- 结果限制: 每个工具可配置（通常 5-10 项）

## 未来增强

潜在添加：
1. 更多 LLM 功能集成
2. 数据库搜索集成
3. 邮件集成（Gmail、Outlook）
4. Slack/Discord 集成
5. GitHub API 集成
6. 实时数据流支持

## MCP 集成

服务器使用 FastMCP 和 stdio 传输，兼容：
- Claude Desktop
- 其他 MCP 兼容客户端
- 通过 stdio 通信的自定义集成

## 文档

提供的全面文档：
- `README.md`: 概述和快速开始
- `SETUP.md`: 详细安装说明
- `QUICK_START.md`: 快速开始指南
- `TOOL_REFERENCE.md`: 所有工具的完整 API 参考
- `ARCHITECTURE.md`: 系统架构和设计
- `CHANGES.md`: 更新和变更日志
- `INDEX.md`: 导航索引
- `PROJECT_SUMMARY.md`: 本文件

## 代码质量

- 全面的类型提示
- 全面的文档字符串
- 一致的格式化
- 各级别的错误处理
- 用于调试的日志记录
- 完整的中文注释

## 维护

添加新工具：
1. 在适当的模块中创建函数
2. 遵循现有模式（async、ActionResponse）
3. 在 `main.py` 中使用 `@mcp.tool` 装饰器注册
4. 更新文档

## 成功指标

✅ 40+ 工具，9 个类别
✅ 遵循 SOLID 原则的模块化架构
✅ 全面的错误处理
✅ 完整的中文文档
✅ 简单的配置和设置
✅ MCP 兼容服务器，可用于生产
✅ 统一的 LLM 客户端集成
✅ 多数工具免费，无需 API 密钥

## 状态

**实现**: 完成
**文档**: 完成（中文）
**测试框架**: 完成
**可使用**: 是（需要依赖安装）
