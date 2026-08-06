# 感知工具 MCP 服务器 - 完整索引

## 快速导航

### 入门指南
- [README.md](README.md) - 项目概述和介绍
- [SETUP.md](SETUP.md - 详细安装和配置说明
- [quickstart.py](quickstart.py) - 测试工具的演示脚本

### 文档
- [TOOL_REFERENCE.md](TOOL_REFERENCE.md) - 所有工具的完整 API 参考
- [ARCHITECTURE.md](ARCHITECTURE.md) - 系统架构和设计
- [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) - 实现摘要
- [CHANGES.md](CHANGES.md) - 更新和变更日志
- [QUICK_START.md](QUICK_START.md) - 快速开始指南

### 配置
- [requirements.txt](requirements.txt) - Python 依赖
- [env.example](env.example) - 环境变量模板

### 源代码
- [src/main.py](src/main.py) - MCP 服务器入口（工具注册）
- [src/base.py](src/base.py) - 共享工具和模型
- [src/search_tools.py](src/search_tools.py) - 搜索功能（3 个工具）
- [src/multimodal_tools.py](src/multimodal_tools.py) - 多模态处理（4 个工具）
- [src/filesystem_tools.py](src/filesystem_tools.py) - 文件操作（3 个工具）
- [src/media_processing_tools.py](src/media_processing_tools.py) - 媒体处理（9 个工具）
- [src/public_data_tools.py](src/public_data_tools.py) - 公共 API（9 个工具）
- [src/private_data_tools.py](src/private_data_tools.py) - 私有数据（2 个工具）

### 测试
- [test_imports.py](test_imports.py) - 验证模块导入
- [test_new_tools.py](test_new_tools.py) - 测试新工具

## 项目统计

- **总文件数**: 30+
- **Python 模块**: 17
- **代码行数**: ~5,000
- **总工具数**: 40+
- **工具类别**: 9
- **文档页面**: 8
- **集成的外部 API**: 10+

## 工具类别概览

### 🔍 搜索工具 (3)
1. **web_search** - DuckDuckGo 网络搜索
2. **download** - 文件下载
3. **knowledge_base_search** - 本地搜索

### 📄 多模态理解 (6)
4. **webpage_reader** - 网页内容提取
5. **document_reader** - PDF/DOCX/PPTX
6. **image_parser** - 图片分析
7. **video_parser** - 视频元数据
8. **youtube_transcript** - YouTube 字幕
9. **youtube_download** - YouTube 视频下载

### 📁 文件系统工具 (3)
10. **file_reader** - 读取文件
11. **grep** - 模式搜索
12. **text_summarizer** - 文本摘要（支持 LLM）

### 🌐 公共数据源 (9)
13. **weather** - 天气信息（Open-Meteo）
14. **stock_price** - 股票数据（Yahoo Finance）
15. **currency_converter** - 货币转换
16. **crypto_price** - 加密货币价格（CoinGecko）
17. **wikipedia_search** - Wikipedia
18. **arxiv_search** - ArXiv 论文
19. **wayback_search** - Wayback Machine
20. **location_search** - 位置搜索（OpenStreetMap）
21. **poi_search** - 兴趣点搜索（OpenStreetMap）

### 🎬 媒体处理 (9)
22. **audio_transcribe** - 音频转录（Whisper）
23. **audio_metadata** - 音频元数据
24. **image_ocr** - 图片 OCR 识别
25. **image_analyze** - AI 图片分析
26. **video_keyframes** - 视频关键帧
27. **video_analyze** - AI 视频分析
28. **audio_trim** - 音频裁剪
29. **image_metadata** - 图片元数据

### 🔬 科学数据 (3)
30. **pubchem_search** - PubChem 化合物搜索
31. **pubchem_properties** - 化合物属性
32. **pubchem_synonyms** - 化合物同义词

### 📈 金融数据 (4)
33. **yfinance_quote** - 股票报价
34. **yfinance_historical** - 历史数据
35. **yfinance_company_info** - 公司信息
36. **yfinance_financials** - 财务报表

### 📄 文档处理 (4)
37. **pdf_extract** - PDF 文本提取
38. **docx_extract** - DOCX 内容提取
39. **pptx_extract** - PPTX 内容提取
40. **csv_parse** - CSV 数据解析

### 🔐 私有数据源 (2)
41. **calendar_events** - Google Calendar
42. **notion_search** - Notion 工作区

## API 依赖

### 需要配置（用于 AI 功能）
- LLM API（文本摘要、图片分析等）

### 可选
- Google Calendar API（日历事件）
- Notion API（Notion 搜索）

### 无需 API 密钥
- DuckDuckGo（网络搜索）
- Open-Meteo（天气）
- Yahoo Finance（股票）
- CoinGecko（加密货币）
- ExchangeRate-API（货币）
- Wikipedia
- ArXiv
- Wayback Machine
- OpenStreetMap（位置和 POI）
- YouTube（字幕和下载）

## 常见任务

### 安装
```bash
cd /home/jackluo/my/ai-agent/ai-agant/chapter4/perception-tools
source /home/jackluo/my/ai-agent/ai-agant/.venv/bin/activate
pip install -r requirements.txt
```

### 测试
```bash
python test_imports.py  # 验证导入
python quickstart.py    # 测试功能
python test_new_tools.py  # 测试新工具
```

### 运行
```bash
cd src
python main.py  # 启动 MCP 服务器
```

### 添加到 Claude Desktop
编辑配置文件并添加：
```json
{
  "mcpServers": {
    "perception-tools": {
      "command": "python",
      "args": ["/home/jackluo/my/ai-agent/ai-agant/chapter4/perception-tools/src/main.py"]
    }
  }
}
```

## 文档结构

### 面向用户
1. 从 [README.md](README.md) 开始
2. 按照 [SETUP.md](SETUP.md) 进行配置
3. 运行 [quickstart.py](quickstart.py) 测试
4. 参考 [TOOL_REFERENCE.md](TOOL_REFERENCE.md) 了解 API 详情

### 面向开发者
1. 查看 [ARCHITECTURE.md](ARCHITECTURE.md) 了解设计
2. 阅读 [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) 了解实现
3. 研究 `src/` 目录中的源代码
4. 添加新工具时遵循现有模式

## 文件用途

| 文件 | 用途 | 面向对象 |
|------|------|----------|
| README.md | 概述、功能、基本用法 | 最终用户 |
| SETUP.md | 安装和配置 | 最终用户 |
| TOOL_REFERENCE.md | 完整 API 文档 | 最终用户、开发者 |
| ARCHITECTURE.md | 系统设计和结构 | 开发者 |
| PROJECT_SUMMARY.md | 实现细节 | 开发者、审查者 |
| CHANGES.md | 更新和变更 | 所有用户 |
| QUICK_START.md | 快速开始 | 所有用户 |
| INDEX.md | 本文件 - 导航辅助 | 所有人 |
| requirements.txt | Python 依赖 | 安装 |
| env.example | 配置模板 | 配置 |
| quickstart.py | 演示和测试 | 测试 |
| test_imports.py | 导入验证 | 测试 |

## 模块用途

| 模块 | 工具数 | 用途 |
|--------|-------|---------|
| main.py | 40+ | MCP 服务器和工具注册 |
| base.py | - | 共享工具和模型 |
| search_tools.py | 3 | 搜索和下载操作 |
| multimodal_tools.py | 6 | 文档和媒体处理 |
| filesystem_tools.py | 3 | 文件系统操作 |
| media_processing_tools.py | 9 | 音视频和图片处理 |
| public_data_tools.py | 9 | 公共 API 集成 |
| private_data_tools.py | 2 | 私有数据源 |
| document_processing_tools.py | 4 | 文档处理 |
| pubchem_tools.py | 3 | 化学数据 |
| yahoo_finance_tools.py | 4 | 金融数据 |
| google_search_enhanced.py | 2 | Google 搜索 |
| wiki_enhanced.py | 4 | Wikipedia 增强 |
| arxiv_enhanced.py | 3 | ArXiv 增强 |
| wayback_enhanced.py | 1 | Wayback 增强 |

## 关键设计决策

1. **模块化架构**: 每个类别使用独立文件
2. **全面异步**: 所有工具使用 async/await
3. **标准化响应**: 统一使用 ActionResponse 格式
4. **全面错误处理**: Try-except 配合详细错误信息
5. **环境变量配置**: 无硬编码凭据
6. **可选依赖**: 核心工具可在没有所有 API 的情况下工作
7. **类型提示**: 完整的类型注释以支持 IDE
8. **中文文档**: 完整的中文注释和文档
9. **统一 LLM 客户端**: 使用项目统一的 LLM 配置

## 支持的格式

### 文档
- PDF, DOCX, PPTX, TXT, MD, JSON, CSV

### 图片
- JPG, PNG, GIF, BMP, TIFF, WEBP

### 视频
- MP4, AVI, MOV, MKV, WEBM

### 音频
- MP3, WAV, AAC, FLAC, OGG

### 网络
- HTML, HTTP/HTTPS URLs

## 外部服务集成

| 服务 | 工具 | 需要 API | 状态 |
|---------|------|----------|--------|
| DuckDuckGo | web_search | 否 | 已实现 |
| Open-Meteo | weather | 否 | 已实现 |
| Yahoo Finance | stock_price | 否 | 已实现 |
| CoinGecko | crypto_price | 否 | 已实现 |
| ExchangeRate-API | currency_converter | 否 | 已实现 |
| Wikipedia | wikipedia_search | 否 | 已实现 |
| ArXiv | arxiv_search | 否 | 已实现 |
| Wayback Machine | wayback_search | 否 | 已实现 |
| OpenStreetMap | location_search/poi_search | 否 | 已实现 |
| YouTube | youtube_transcript/download | 否 | 已实现 |
| Google Calendar | calendar_events | 是（OAuth2） | 已实现 |
| Notion | notion_search | 是 | 已实现 |
| LLM Providers | text_summarizer/image_analyze | 是 | 已实现 |

## 开发时间线

✅ 阶段 1: 项目结构和基础工具
✅ 阶段 2: 搜索工具实现
✅ 阶段 3: 多模态工具实现
✅ 阶段 4: 文件系统工具实现
✅ 阶段 5: 公共数据工具实现
✅ 阶段 6: 私有数据工具实现
✅ 阶段 7: 媒体处理工具实现
✅ 阶段 8: 文档和测试
✅ 阶段 9: 中文化改造
✅ 阶段 10: 集成和验证

## 用户后续步骤

1. ✅ 阅读 README.md
2. ⬜ 安装依赖
3. ⬜ 配置 LLM（如需使用 AI 功能）
4. ⬜ 运行 test_imports.py
5. ⬜ 运行 quickstart.py
6. ⬜ 与 MCP 客户端集成
7. ⬜ 开始使用工具！

## 支持资源

- **文档**: 本目录中的所有 .md 文件
- **源代码**: src/ 中有详细注释的代码
- **测试**: test_imports.py 和 quickstart.py
- **配置**: 带有详细注释的 env.example

## 许可与归属

AI Agent 训练营材料的一部分。

---

**最后更新**: 2024
**版本**: 2.0.0
**状态**: 完成并可用
