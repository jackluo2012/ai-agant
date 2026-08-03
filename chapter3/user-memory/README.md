# 用户记忆系统

> 长期用户记忆系统：对话与后台记忆处理分离、多种记忆模式、支持多提供商。
> 配套《深入理解 AI Agent》第 3 章内容，已迁移至 ai-agant 项目规范。

← [返回项目根目录](../../README.md) | [返回第 3 章](../README.md)

---

## 关键特性

- **分离架构**：对话 Agent 与后台记忆处理器解耦
- **多种记忆模式**：简单笔记 → 增强笔记 → JSON 卡片 → 高级 JSON 卡片
- **统一 LLM 客户端**：使用项目级 LLM 配置
- **React + 工具** 结构化记忆操作
- **流式输出**、**按间隔后台更新**、**JSON 持久化**

## 安装

Python 3.8+，在项目根目录配置 LLM。

```bash
# 从项目根目录
cd ai-agant
pip install -r requirements.txt  # 安装核心依赖

# 安装 user-memory 特定依赖
pip install -r chapter3/user-memory/requirements.txt

# 在项目根目录 .env 中配置 LLM
cp .env.example .env
# 编辑 .env: API_KEY, LLM_PROVIDER, LLM_MODEL
```

## 快速开始

```bash
# 激活虚拟环境
cd ai-agant
source .venv/bin/activate

# 运行快速开始
python3 chapter3/user-memory/quickstart.py

# 交互模式
python3 chapter3/user-memory/main.py --mode interactive --user your_name
# 命令: memory | process | save | reset | quit/exit

# 演示模式
python3 chapter3/user-memory/main.py --mode demo --memory-mode enhanced_notes

# 评估模式
python3 chapter3/user-memory/main.py --mode evaluation --memory-mode advanced_json_cards
```

## 架构

用户界面 → **ConversationalAgent**（对话、读记忆、流式）+ **BackgroundMemoryProcessor**（分析并写记忆）→ **MemoryManager**（笔记/JSON 卡片）。

**核心文件：**`conversational_agent.py`、`background_memory_processor.py`、`agent.py`、`memory_manager.py`。

## 记忆模式

1. **`notes`** — 短事实
2. **`enhanced_notes`** — 带上下文的段落
3. **`json_cards`** — 层次化 JSON
4. **`advanced_json_cards`** — 含 backstory / person / relationship 等完整卡片

## LLM 配置

本项目使用统一的 LLM 客户端。在项目根目录 `.env` 中配置：

```bash
# 在 ai-agant/.env 中
API_KEY=your_api_key_here
LLM_PROVIDER=kimi  # 或 openai, deepseek, anthropic 等
LLM_MODEL=kimi-k3
BASE_URL=  # 可选，用于自定义提供商
```

## 编程接口

```python
from conversational_agent import ConversationalAgent, ConversationConfig
from config import MemoryMode

agent = ConversationalAgent(
    user_id="user123",
    # 使用项目 .env 中的提供商和模型配置
    config=ConversationConfig(enable_memory_context=True, temperature=0.7),
    memory_mode=MemoryMode.ENHANCED_NOTES
)
response = agent.chat("你好，我是张三，我在腾讯公司工作")
```

```python
from agent import UserMemoryAgent, UserMemoryConfig

agent = UserMemoryAgent(
    user_id="user123",
    # 使用项目级 LLM 配置
    config=UserMemoryConfig(enable_memory_updates=True, memory_mode=MemoryMode.ADVANCED_JSON_CARDS)
)
result = agent.execute_task("记住我偏好 Python，邮箱是 zhangsan@example.com")
```

## 高级配置

```bash
# 用户记忆特定配置（在 chapter3/user-memory/.env 或项目根目录）
MEMORY_MODE=enhanced_notes
MAX_MEMORY_ITEMS=100
MEMORY_UPDATE_TEMPERATURE=0.2
SESSION_TIMEOUT=3600
MAX_CONTEXT_LENGTH=8000
```

## 项目结构

```
chapter3/user-memory/
├── main.py, quickstart.py, agent.py
├── conversational_agent.py, background_memory_processor.py
├── memory_manager.py, config.py, conversation_history.py
├── memory_operation_formatter.py, run_evaluation.py
├── requirements.txt
├── data/{memories,conversations}/, logs/, results/
```

## 运行说明

**虚拟环境位置：** `.venv/`（项目根目录）

**正确运行方式：**

```bash
# 从项目根目录运行（推荐）
cd ai-agant
source .venv/bin/activate
python3 chapter3/user-memory/quickstart.py
```

---

## 迁移说明

本项目已从 `ai-agent-book/chapter3/user-memory` 迁移至 `ai-agant/chapter3/user-memory`，遵循 ai-agant 项目规范。

### 主要变更

1. **LLM 客户端**：使用 `llm.client.get_llm_client()` 代替各模块的独立初始化
2. **配置**：LLM 相关配置移至项目根目录 `.env`
3. **依赖**：核心依赖（openai, python-dotenv）由根目录统一管理
4. **代码**：所有提示词、注释和用户可见内容已完全中文化

### 向后兼容

如需使用原来的配置方式，可以恢复 `env.example` 中独立配置，但建议使用项目级配置以保持一致性。

---

## License

教学材料。
