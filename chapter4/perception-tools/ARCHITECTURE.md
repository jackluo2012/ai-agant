# 架构概述

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     MCP 客户端（如 Claude）                      │
└───────────────────────────────┬─────────────────────────────────┘
                                │ stdio
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                        main.py (FastMCP)                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              工具注册 (@mcp.tool)                         │   │
│  └──────────────────────────────────────────────────────────┘   │
└───┬──────┬──────────┬──────────┬────────────┬──────────────┬───┘
    │      │          │          │            │              │
┌───▼──┐ ┌─▼────┐ ┌──▼──┐ ┌─────▼────┐ ┌────▼─────┐ ┌──────▼────┐
│搜索 │ │多模 │ │文件 │ │  公共    │ │  私有    │ │   基础    │
│工具 │ │态   │ │系统 │ │  数据    │ │  数据    │ │   工具    │
│ (3) │ │工具 │ │工具 │ │ 工具(6) │ │ 工具(2) │ │           │
│      │ │ (4) │ │ (3) │ │          │ │          │ │           │
└───┬──┘ └─┬────┘ └──┬──┘ └─────┬────┘ └────┬─────┘ └──────┬────┘
    │      │         │          │            │              │
    │      │         │          │            │              │
    └──────┴─────────┴──────────┴────────────┴──────────────┘
                                │
                    ┌───────────▼───────────┐
                    │  ActionResponse 模型  │
                    │  (标准化输出格式)     │
                    └───────────────────────┘
```

## 模块依赖关系

```
main.py
├── search_tools.py
│   ├── base.py (ActionResponse, is_url, download_file_from_url)
│   ├── requests
│   └── mcp.types (TextContent)
│
├── multimodal_tools.py
│   ├── base.py (ActionResponse, validate_file_path, download_file_from_url)
│   ├── beautifulsoup4
│   ├── PyPDF2
│   ├── python-docx
│   ├── python-pptx
│   ├── Pillow
│   └── opencv-python
│
├── filesystem_tools.py
│   ├── base.py (ActionResponse, validate_file_path)
│   └── re (标准库)
│
├── public_data_tools.py
│   ├── base.py (ActionResponse)
│   ├── requests
│   ├── wikipedia
│   └── arxiv
│
├── private_data_tools.py
│   ├── base.py (ActionResponse)
│   ├── google-api-python-client (可选)
│   └── notion-client (可选)
│
└── base.py
    ├── pydantic (BaseModel, Field)
    └── requests
```

## 数据流

### 请求流程
```
1. MCP 客户端通过 stdio 发送工具请求
   ↓
2. FastMCP 服务器接收并验证请求
   ↓
3. 调用相应的工具函数
   ↓
4. 工具函数处理请求
   ↓
5. 外部 API 调用（如需要）
   ↓
6. 数据处理和转换
   ↓
7. 创建 ActionResponse 对象
   ↓
8. 包装为 TextContent
   ↓
9. JSON 序列化并通过 stdio 返回
   ↓
10. MCP 客户端接收并处理响应
```

### 错误处理流程
```
1. 工具函数中发生异常
   ↓
2. 在 try-except 块中捕获异常
   ↓
3. 记录错误日志和堆栈信息
   ↓
4. 创建 success=False 的 ActionResponse
   ↓
5. 错误详细信息放入 message 和 metadata
   ↓
6. 返回给客户端（不会崩溃）
```

## 组件职责

### main.py
- **角色**: MCP 服务器初始化和工具注册
- **职责**:
  - 初始化 FastMCP 服务器
  - 使用装饰器注册所有工具函数
  - 提供服务器级别的说明
  - 运行 stdio 传输循环
- **依赖**: 所有工具模块

### base.py
- **角色**: 共享工具和模型
- **职责**:
  - 定义 ActionResponse 模型
  - 定义 DocumentMetadata 模型
  - 提供 URL 验证 (is_url)
  - 提供文件验证 (validate_file_path)
  - 提供文件下载工具 (download_file_from_url)
- **依赖**: pydantic, requests

### search_tools.py
- **角色**: 搜索和检索操作
- **工具**:
  - web_search: DuckDuckGo 网络搜索
  - download_file: HTTP/HTTPS 文件下载
  - search_knowledge_base: 本地文件搜索
- **外部 API**: DuckDuckGo
- **依赖**: requests, base

### multimodal_tools.py
- **角色**: 从各种媒体提取内容
- **工具**:
  - read_webpage: HTML 解析
  - read_document: 文档提取 (PDF/DOCX/PPTX)
  - parse_image: 图片元数据和分析
  - parse_video: 视频元数据提取
- **文件格式**: HTML, PDF, DOCX, PPTX, JPG, PNG, MP4 等
- **依赖**: beautifulsoup4, PyPDF2, python-docx, python-pptx, Pillow, opencv-python, base

### filesystem_tools.py
- **角色**: 文件系统操作
- **工具**:
  - read_file: 读取文件内容
  - grep_search: 文件中的模式搜索
  - summarize_text: 文本摘要
- **依赖**: re (标准库), base

### public_data_tools.py
- **角色**: 公共 API 集成
- **工具**:
  - get_weather: Open-Meteo 天气 API
  - get_stock_price: Yahoo Finance
  - convert_currency: 汇率 API
  - search_wikipedia: Wikipedia API
  - search_arxiv: ArXiv API
  - search_wayback: Wayback Machine API
- **外部 API**: 6 个不同的公共 API
- **依赖**: requests, wikipedia, arxiv, base

### private_data_tools.py
- **角色**: 私有数据源集成
- **工具**:
  - get_calendar_events: Google Calendar OAuth2
  - search_notion: Notion API
- **外部 API**: Google Calendar, Notion
- **依赖**: google-api-python-client (可选), notion-client (可选), base

## 配置管理

```
环境变量 (.env)
├── API_KEY (LLM 调用必需)
├── LLM_PROVIDER (LLM 提供商)
├── LLM_MODEL (模型名称)
├── BASE_URL (API 基础 URL)
├── NOTION_API_KEY (Notion 可选)
└── Google OAuth2 凭证 (日历可选)
```

## 错误处理策略

### 错误处理层级

1. **输入验证**
   - 参数验证
   - 文件存在性检查
   - URL 格式验证

2. **外部 API 错误**
   - 网络超时
   - HTTP 错误
   - API 配额限制
   - 认证失败

3. **处理错误**
   - 文件解析错误
   - 编码错误
   - 内存限制

4. **优雅降级**
   - 可能时返回部分结果
   - 清晰的错误消息
   - 建议补救措施

### 错误响应格式
```json
{
  "success": false,
  "message": "人类可读的错误描述",
  "metadata": {
    "error_type": "错误类别",
    "additional_context": "更多细节"
  }
}
```

## 性能特征

### 超时设置
- Web 请求: 10-30 秒
- 文件下载: 180 秒
- 长时间操作: 300 秒

### 限制
- 文件下载大小: 100 MB
- 视频下载大小: 500 MB
- 文本读取限制: 50,000 字符
- 搜索结果: 5-100 条

### 并发
- 全面使用 async/await
- 单线程 stdio 传输
- 非阻塞外部 API 调用

## 安全考虑

### 输入验证
- 防止路径遍历攻击
- URL 方案限制（仅 HTTP/HTTPS）
- 文件大小限制
- 强制执行超时

### API 安全
- 通过环境变量存储 API 密钥
- Google Calendar 使用 OAuth2
- Notion 使用基于令牌的认证
- 无硬编码凭据

### 输出清理
- 所有响应使用 JSON 编码
- 二进制数据使用 Base64 编码
- 返回数据长度限制

## 扩展点

### 添加新工具
1. 在适当模块中创建函数
2. 遵循 async 模式
3. 使用 ActionResponse 格式
4. 添加错误处理
5. 在 main.py 中注册
6. 更新文档

### 添加新类别
1. 在 src/ 中创建新模块
2. 导入基础工具
3. 按照模式实现工具
4. 在 main.py 中导入
5. 注册工具
6. 更新文档

### 添加新数据源
1. 添加到 public_data_tools.py 或 private_data_tools.py
2. 实现 API 客户端
3. 遵循错误处理模式
4. 记录 API 要求
5. 更新 env.example

## 测试策略

### 单元测试（未来）
- 测试每个工具函数
- 模拟外部 API
- 测试错误条件
- 验证响应格式

### 集成测试
- test_imports.py: 验证所有导入
- quickstart.py: 测试实际功能
- 通过 MCP 客户端手动测试

### 生产监控
- 全面的日志记录
- 错误跟踪
- 性能指标（计时）
- API 配额监控

## 部署考虑

### 要求
- Python 3.10+
- requirements.txt 中的所有依赖
- 配置环境变量
- 外部 API 的网络访问

### 生产环境运行
- 使用进程管理器（systemd、supervisor）
- 配置适当的超时
- 监控日志
- 设置 API 密钥轮换
- 如需要实现速率限制

### 扩展
- 当前: 单进程，stdio 传输
- 未来: 可添加 HTTP 传输支持多客户端
- 未来: 可实现缓存层
- 未来: 可添加请求队列
