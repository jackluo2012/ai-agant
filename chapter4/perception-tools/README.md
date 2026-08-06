# 感知工具 MCP 服务器

全面的感知和数据检索 MCP 服务器，为 AI Agent 提供丰富的感知能力。

> **配套《深入理解 AI Agent》第 4 章实验项目**

[返回第 4 章目录](../README.md)

## 📋 功能概述

### 🔍 搜索工具
- **网络搜索**：使用 DuckDuckGo 进行免费网络搜索（无需 API 密钥）
- **知识库搜索**：搜索本地文件目录
- **文件下载**：从 URL 下载文件到本地

### 🌐 多模态理解
- **网页读取**：提取网页文本和链接
- **文档解析**：支持 PDF、DOCX、PPTX 格式
- **图片解析**：提取图片信息和元数据
- **视频解析**：提取视频元数据和关键帧

### 📁 文件系统
- **文件读取**：支持多种编码的文件读取
- **模式搜索**：类 grep 的正则表达式搜索
- **智能摘要**：支持 LLM 的文本摘要

### 📊 公开数据源
- **天气信息**：Open-Meteo 天气数据
- **股票价格**：实时股票市场数据
- **加密货币**：CoinGecko 价格数据
- **货币转换**：实时汇率转换
- **位置搜索**：Nominatim 地理编码
- **兴趣点**：Overpass POI 搜索
- **Wikipedia**：百科知识搜索
- **ArXiv**：学术论文检索

### 📺 YouTube 工具
- **字幕提取**：提取视频字幕（支持多语言）
- **视频下载**：使用 yt-dlp 下载视频

### 🔬 科学数据
- **PubChem**：化学化合物查询
- **分子属性**：获取化合物详细信息

### 📈 金融数据
- **股票报价**：Yahoo Finance 数据
- **历史数据**：历史价格查询
- **财务报表**：公司财务数据

### 🎬 媒体处理
- **音频转录**：Whisper 语音识别
- **图片 OCR**：文字提取识别
- **AI 视觉**：图片和视频分析
- **音频处理**：裁剪和元数据提取

## 🚀 快速开始

### 1. 环境准备

确保已创建项目虚拟环境：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r chapter4/perception-tools/requirements.txt
```

### 3. 配置 LLM（可选）

如需使用 AI 功能（文本摘要、图片分析等），在项目根目录的 `.env` 文件中配置：

```bash
# LLM 配置
API_KEY=your_api_key
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
BASE_URL=https://api.openai.com/v1
```

支持的提供商：
- Kimi (Moonshot): `LLM_PROVIDER=kimi`, `LLM_MODEL=kimi-k3`
- OpenAI: `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-4o`
- DeepSeek: `LLM_PROVIDER=deepseek`, `LLM_MODEL=deepseek-chat`
- 阿里云: `LLM_PROVIDER=aliyun`, `LLM_MODEL=qwen-max`

### 4. 运行服务器

```bash
cd chapter4/perception-tools
python src/main.py
```

## 📖 使用示例

### 作为 MCP 客户端使用

```python
from mcp import ClientSession, StdioServerParameters
import asyncio

async def main():
    async with ClientSession(
        StdioServerParameters(
            command="python",
            args=["src/main.py"]
        )
    ) as session:
        # 初始化
        await session.initialize()

        # 网络搜索
        result = await session.call_tool("web_search", {
            "query": "Python 编程教程",
            "num_results": 5
        })
        print(result)

        # 文本摘要
        result = await session.call_tool("text_summarizer", {
            "text": "长文本内容...",
            "max_length": 200,
            "use_llm": True
        })

        # 图片分析
        result = await session.call_tool("image_analyze", {
            "image_path": "/path/to/image.jpg",
            "prompt": "请描述图片中的主要物体"
        })

asyncio.run(main())
```

### Claude Desktop 配置

在 Claude Desktop 的配置文件中添加：

```json
{
  "mcpServers": {
    "perception-tools": {
      "command": "python",
      "args": ["/path/to/ai-agant/chapter4/perception-tools/src/main.py"]
    }
  }
}
```

## 🛠️ 可用工具列表

### 搜索类
| 工具名 | 功能描述 | 是否需要 API Key |
|--------|----------|------------------|
| `web_search` | DuckDuckGo 网络搜索 | ❌ 免费 |
| `download` | URL 文件下载 | ❌ 免费 |
| `knowledge_base_search` | 本地知识库搜索 | ❌ 免费 |

### 多模态类
| 工具名 | 功能描述 | 是否需要 API Key |
|--------|----------|------------------|
| `webpage_reader` | 网页内容提取 | ❌ 免费 |
| `document_reader` | 文档解析（PDF/DOCX/PPTX） | ❌ 免费 |
| `image_parser` | 图片信息解析 | ❌ 免费 |
| `video_parser` | 视频元数据提取 | ❌ 免费 |
| `image_analyze` | AI 图片分析 | ✅ 需要 |
| `video_analyze` | AI 视频分析 | ✅ 需要 |

### 文件系统类
| 工具名 | 功能描述 | 是否需要 API Key |
|--------|----------|------------------|
| `file_reader` | 文件读取 | ❌ 免费 |
| `grep` | 正则表达式搜索 | ❌ 免费 |
| `text_summarizer` | 智能文本摘要 | ✅ 需要（可选） |

### 数据源类
| 工具名 | 功能描述 | 是否需要 API Key |
|--------|----------|------------------|
| `weather` | 天气信息查询 | ❌ 免费 |
| `stock_price` | 股票价格查询 | ❌ 免费 |
| `crypto_price` | 加密货币价格 | ❌ 免费 |
| `currency_converter` | 货币汇率转换 | ❌ 免费 |
| `wikipedia_search` | Wikipedia 搜索 | ❌ 免费 |
| `arxiv_search` | ArXiv 论文搜索 | ❌ 免费 |
| `location_search` | 地理编码 | ❌ 免费 |
| `poi_search` | 兴趣点搜索 | ❌ 免费 |

### YouTube 类
| 工具名 | 功能描述 | 是否需要 API Key |
|--------|----------|------------------|
| `youtube_transcript` | 视频字幕提取 | ❌ 免费 |
| `youtube_download` | 视频下载 | ❌ 免费 |

### 媒体处理类
| 工具名 | 功能描述 | 是否需要 API Key |
|--------|----------|------------------|
| `audio_transcribe` | 音频转录（Whisper） | ✅ 需要 |
| `image_ocr` | 图片文字识别 | ❌ 免费（需 tesseract） |
| `audio_trim` | 音频裁剪 | ❌ 免费（需 ffmpeg） |

## 🔧 配置说明

### 环境变量

在项目根目录 `.env` 文件中配置：

| 变量名 | 说明 | 必需 |
|--------|------|------|
| `API_KEY` | LLM API 密钥 | AI 功能必需 |
| `LLM_PROVIDER` | LLM 提供商 | AI 功能必需 |
| `LLM_MODEL` | 模型名称 | AI 功能必需 |
| `BASE_URL` | API 基础 URL | 某些提供商必需 |

## 📦 依赖说明

### 核心依赖（由项目根目录提供）
- `mcp` - MCP 框架
- `pydantic` - 数据验证
- `python-dotenv` - 环境变量
- `openai` - LLM 客户端

### 模块依赖（需要安装）
- `requests` - HTTP 请求
- `beautifulsoup4` - HTML 解析
- `PyPDF2` - PDF 处理
- `python-docx` - DOCX 处理
- `opencv-python` - 视频处理
- `youtube-transcript-api` - YouTube 字幕
- `wikipedia` - Wikipedia API
- `yfinance` - 金融数据

### 可选依赖
- `openai-whisper` - 本地 Whisper 模型
- `pytesseract` - OCR 功能（需要系统安装 tesseract-ocr）

## 🏗️ 项目结构

```
perception-tools/
├── src/
│   ├── main.py                    # MCP 服务器入口
│   ├── base.py                    # 基础模块和响应格式
│   ├── search_tools.py            # 搜索工具
│   ├── multimodal_tools.py        # 多模态工具
│   ├── filesystem_tools.py        # 文件系统工具
│   ├── media_processing_tools.py  # 媒体处理工具
│   ├── public_data_tools.py       # 公共数据源
│   ├── private_data_tools.py      # 私有数据源
│   ├── document_processing_tools.py  # 文档处理
│   ├── pubchem_tools.py           # 化学数据
│   ├── yahoo_finance_tools.py    # 金融数据
│   ├── google_search_enhanced.py  # Google 搜索
│   ├── wiki_enhanced.py           # Wikipedia 增强
│   ├── arxiv_enhanced.py          # ArXiv 增强
│   └── wayback_enhanced.py        # Wayback Machine
├── requirements.txt               # 依赖列表
├── README.md                       # 本文档
├── logs/                           # 日志目录
└── results/                        # 结果输出目录
```

## 🎯 设计原则

### 代码规范
- ✅ 使用项目统一的 LLM 客户端封装
- ✅ 所有提示词和响应使用中文
- ✅ 完整的中文注释和文档
- ✅ 统一的响应格式（ActionResponse）
- ✅ 完善的错误处理和日志

### 中文化要求
- ✅ 用户可见的提示词全部中文化
- ✅ 工具描述和说明使用中文
- ✅ 错误消息使用中文
- ✅ 代码注释使用中文

### LLM 调用封装
- ✅ 统一使用 `llm.client.get_llm_client()`
- ✅ 支持多种 LLM 提供商
- ✅ 自动回退机制
- ✅ 清晰的错误提示

## 🔍 故障排除

### LLM 相关问题

**问题**: `ValueError: API 密钥未设置`

**解决**: 在项目根目录 `.env` 文件中配置：
```bash
API_KEY=your_api_key
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
```

### YouTube 相关问题

**问题**: `youtube-transcript-api 无法获取字幕`

**解决**: 某些视频可能没有字幕，或字幕被禁用。尝试其他视频或检查视频是否支持字幕。

### OCR 相关问题

**问题**: `pytesseract 未安装`

**解决**:
```bash
# Python 包
pip install pytesseract

# 系统依赖（Ubuntu/Debian）
sudo apt-get install tesseract-ocr

# 系统依赖（macOS）
brew install tesseract
```

### ffmpeg 相关问题

**问题**: `ffmpeg 命令未找到`

**解决**:
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg
```

## 📝 开发指南

### 添加新工具

1. 在对应的模块文件中添加函数
2. 使用 `ActionResponse` 统一响应格式
3. 添加完整的中文文档字符串
4. 在 `main.py` 中注册为 MCP 工具

示例：

```python
# 在 my_tools.py 中
async def my_new_tool(param1: str, param2: int) -> Union[str, TextContent]:
    """
    工具功能描述

    Args:
        param1: 参数1说明
        param2: 参数2说明

    Returns:
        返回值说明
    """
    try:
        # 实现逻辑
        result = {"key": "value"}

        action_response = ActionResponse(
            success=True,
            message=result,
            metadata={}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        # 错误处理
        pass

# 在 main.py 中
@mcp.tool(description="工具描述")
async def my_tool(
    param1: str = Field(description="参数1"),
    param2: int = Field(description="参数2")
):
    """工具说明"""
    return await my_new_tool(param1, param2)
```

### 使用 LLM

```python
from llm.client import get_llm_client

# 获取客户端
client = get_llm_client()

# 调用
response = client.chat.completions.create(
    model=client.model_name,
    messages=[
        {"role": "system", "content": "系统提示词"},
        {"role": "user", "content": "用户输入"}
    ],
    max_tokens=1000,
    temperature=0.7
)

result = response.choices[0].message.content
```

## 🔗 相关链接

- [MCP 协议文档](https://modelcontextprotocol.io/)
- [项目主目录](../README.md)
- [CONVENTION.md](../../CONVENTION.md)

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**返回项目根目录**: [ai-agant](../..)
