# 安装指南

## 快速安装

1. **进入项目目录:**
   ```bash
   cd /home/jackluo/my/ai-agent/ai-agant/chapter4/perception-tools
   ```

2. **安装依赖:**
   ```bash
   # 激活虚拟环境
   source /home/jackluo/my/ai-agent/ai-agant/.venv/bin/activate

   # 安装依赖
   pip install -r requirements.txt
   ```

3. **配置环境变量（如需使用 AI 功能）:**
   ```bash
   # 在项目根目录的 .env 文件中配置
   # 大多数功能无需 API 密钥即可使用
   ```

4. **测试安装:**
   ```bash
   python test_imports.py
   ```

5. **运行快速演示:**
   ```bash
   python quickstart.py
   ```

6. **启动 MCP 服务器:**
   ```bash
   python src/main.py
   ```

## 详细 API 配置

### LLM 配置（用于 AI 功能）

**注意**: 大多数工具无需 LLM 即可使用。以下配置仅用于文本摘要、图片分析等 AI 功能。

在项目根目录 `.env` 文件中配置：

```bash
# LLM 配置
API_KEY=your_api_key
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
BASE_URL=https://api.openai.com/v1
```

支持的提供商：
- **Kimi (Moonshot)**: `LLM_PROVIDER=kimi`, `LLM_MODEL=kimi-k3`
- **OpenAI**: `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-4o`
- **DeepSeek**: `LLM_PROVIDER=deepseek`, `LLM_MODEL=deepseek-chat`
- **阿里云**: `LLM_PROVIDER=aliyun`, `LLM_MODEL=qwen-max`

### Notion API（可选）

1. 访问 [Notion Integrations](https://www.notion.so/my-integrations)
2. 创建新的集成
3. 复制"Internal Integration Token"
4. 将数据库/页面与集成共享
5. 安装 Notion SDK:
   ```bash
   pip install notion-client
   ```
6. 添加到 `.env`:
   ```
   NOTION_API_KEY=your_integration_token
   ```

### Google Calendar API（可选）

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 启用"Google Calendar API"
3. 创建 OAuth 2.0 凭证
4. 下载凭证 JSON 文件
5. 安装必需的包:
   ```bash
   pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
   ```
6. 运行 OAuth 流程（仅首次）:
   ```python
   # 这将打开浏览器进行认证
   # 令牌将保存到 ~/.perception-tools/google_token.pickle
   ```

## 与 MCP 客户端配合使用

### Claude Desktop 配置

编辑 Claude Desktop 配置文件：

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

**Linux:** `~/.config/Claude/claude_desktop_config.json`

添加服务器配置：

```json
{
  "mcpServers": {
    "perception-tools": {
      "command": "python",
      "args": ["/home/jackluo/my/ai-agent/ai-agant/chapter4/perception-tools/src/main.py"],
      "env": {
        "API_KEY": "your_api_key",
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": "gpt-4o"
      }
    }
  }
}
```

### 其他 MCP 客户端

服务器使用 stdio 传输，可与任何 MCP 兼容客户端集成。请参考客户端文档了解配置详情。

## 故障排除

### 导入错误

如果看到导入错误，确保所有依赖已安装：

```bash
source /home/jackluo/my/ai-agent/ai-agant/.venv/bin/activate
pip install -r requirements.txt
```

### API 错误

如果 API 调用失败：
1. 检查 `.env` 中的 API 密钥是否正确设置
2. 验证您的 API 配额未超限
3. 检查 API 服务状态

### 文件权限错误

确保脚本对以下目录有写权限：
- 下载目录（用于文件下载）
- `~/.perception-tools/`（用于 OAuth 令牌）

### 找不到模块

如果 Python 无法找到模块，确保从正确的目录运行或调整 PYTHONPATH：

```bash
export PYTHONPATH="${PYTHONPATH}:/home/jackluo/my/ai-agent/ai-agant/chapter4/perception-tools/src"
```

## 开发

### 运行测试

```bash
# 测试导入
python test_imports.py

# 测试工具
python quickstart.py

# 测试新工具
python test_new_tools.py
```

### 添加新工具

1. 选择适当的模块（或创建新模块）
2. 按照模式实现工具函数：
   ```python
   async def my_tool(param: str) -> Union[str, TextContent]:
       try:
           # 实现代码
           return TextContent(...)
       except Exception as e:
           # 错误处理
           return TextContent(...)
   ```
3. 使用 `@mcp.tool` 装饰器在 `main.py` 中注册工具
4. 更新文档

### 代码风格

- 遵循 KISS、DRY 和 SOLID 原则
- 使用类型提示
- 为所有函数包含文档字符串
- 返回标准化的 ActionResponse 格式
- 包含全面的错误处理

## 支持

如有问题和疑问：
1. 查看本安装指南
2. 查看主 README.md
3. 查看工具特定文档
4. 查看 API 提供商文档

## 无需 API 密钥的工具

以下工具完全免费，无需任何 API 密钥：

| 工具 | API 来源 |
|------|----------|
| 网络搜索 | DuckDuckGo |
| 天气 | Open-Meteo |
| 股票价格 | Yahoo Finance |
| 加密货币价格 | CoinGecko |
| 货币转换 | ExchangeRate-API |
| 位置搜索 | OpenStreetMap (Nominatim) |
| 兴趣点搜索 | OpenStreetMap (Overpass) |
| Wikipedia | Wikipedia API |
| ArXiv | ArXiv API |
| Wayback Machine | Internet Archive |

这意味着您可以立即开始使用这些工具，无需任何设置！
