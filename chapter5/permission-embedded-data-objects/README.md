# 权限内嵌数据对象

## 功能概述

验证业务代码可以动态生成或重写时，系统仍能保证权限和数据完整性。实验把应用层故意做得很薄：生成的代码只调用稳定的对象存储接口；权限规则、校验器、对象关系和后果声明附着在数据类型上，由对象存储在每次操作时统一检查。

确定性演示包含三类操作：
- 合法的招聘流程更新应当成功
- 跳过候选人状态机或写入超出职位范围的工资应由数据层拒绝
- 跨租户读取应由权限边界拒绝

这个实验关注的不是生成的 handler 有没有写出一条正确的 `if`，而是同一请求到达稳定数据层后能否被可靠接受或拒绝。生成代码只能携带受限的 `AccessContext`，不能拿到可绕过规则的高权限数据库连接。

## 快速开始

### 1. 环境准备

确保已安装：
- Python 3.9+
- PostgreSQL（正在运行并可访问）

### 2. 安装依赖

```bash
cd chapter5/permission-embedded-data-objects
pip install -r requirements.txt
```

### 3. 配置

#### LLM 配置（项目根目录 .env）

在项目根目录（`ai-agant/`）的 `.env` 文件中配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek, openai 等
LLM_MODEL=kimi-k3   # 可选，使用默认模型
```

#### 数据库配置

默认数据库名称：`pedo_test`

可通过环境变量指定连接字符串：
```bash
export PEDO_DSN='dbname=pedo_test host=localhost user=postgres'
```

### 4. 创建数据库

```bash
createdb pedo_test
```

### 5. 运行演示

```bash
# 确定性演示（无需 LLM）
python demo.py

# 运行测试
pytest -q
```

### 6. 运行评测（可选）

在线评测需要配置 LLM：

```bash
# 设置评测数据库
export DATAGUARDBENCH_DSN="$PEDO_DSN"

# 运行跨提供商评测
python run_targeted_eval.py
```

⚠️ **警告**：评测工具会在隔离测试库中执行模型生成的代码，不应直接指向生产数据库。

## 使用方法

### 项目结构

```
permission-embedded-data-objects/
├── demo.py                    # 确定性演示
├── run_targeted_eval.py       # 跨提供商目标评测
├── pedo/
│   ├── core/
│   │   ├── models.py          # 数据模型
│   │   └── store.py           # 三层管道对象存储
│   ├── scenarios/             # 场景定义
│   │   ├── hiring.py          # 招聘流程
│   │   ├── project_mgmt.py    # 项目管理
│   │   └── ...
│   └── eval/
│       └── dataguardbench/    # DataGuardBench 评测框架
└── tests/                     # 核心测试
```

### API 说明

#### 核心模型

```python
from pedo.core.models import DataObject, AccessContext, ObjectType
from pedo.core.store import ObjectStore

# 创建存储
store = ObjectStore("dbname=pedo_test")

# 创建访问上下文
accessor = AccessContext(
    user_id="user1",
    role="recruiter",
    org_id="acme"
)

# 创建对象
obj = DataObject(
    type_name="candidate",
    content={"name": "张三", "status": "applied"},
    org_id="acme"
)
store.create(obj, accessor)

# 读取对象
result = store.get(obj.id, accessor)

# 更新对象
store.update(obj.id, {"status": "screened"}, accessor)

# 删除对象
store.delete(obj.id, accessor)
```

#### 评测框架

```python
# 运行完整评测
from pedo.eval.dataguardbench.harness import run_benchmark

results = run_benchmark(
    models=["claude:claude-sonnet-4-6", "gpt:gpt-4o-mini"],
    conditions=["raw", "pedo"],
    scenarios=["hiring", "project_mgmt"]
)
```

## 配置说明

### LLM 提供商支持

| 提供商 | LLM_PROVIDER | LLM_MODEL 示例 |
|--------|---------------|-----------------|
| Kimi | `kimi` | `kimi-k3` |
| OpenAI | `openai` | `gpt-4o` |
| DeepSeek | `deepseek` | `deepseek-chat` |
| SiliconFlow | `siliconflow` | `Qwen/Qwen2.5-72B-Instruct` |
| 阿里云 | `aliyun` | `qwen-plus` |

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `PEDO_DSN` | PostgreSQL 连接字符串 | `dbname=pedo_test` |
| `DATAGUARDBENCH_DSN` | 评测数据库连接字符串 | 继承 `PEDO_DSN` |

## 故障排除

### 数据库连接错误

```bash
# 检查 PostgreSQL 是否运行
pg_isready

# 检查数据库是否存在
psql -l | grep pedo_test
```

### LLM 调用错误

```bash
# 检查项目根目录 .env 配置
cat ../../.env | grep API_KEY

# 验证 LLM 客户端
python3 -c "from llm.client import get_llm_client; print(get_llm_client())"
```

### 导入错误

确保从项目根目录运行：

```bash
cd /path/to/ai-agant
source .venv/bin/activate
python3 chapter5/permission-embedded-data-objects/demo.py
```

## 技术要点

### 三层管道

1. **第一层（同步）**：权限检查 + 验证器
2. **第二层（同步）**：对象存储机制 + 引用完整性
3. **第三层（异步）**：反应（Reactions）

### 权限规则

- 支持基于角色、用户、组织的访问控制
- 内置租户隔离
- 支持对象级权限覆盖

### 验证器

- 状态机验证
- 数据范围验证
- 跨对象验证

### 反应机制

- 声明式事件驱动
- 受控深度防止无限循环
- 支持同步和异步执行
