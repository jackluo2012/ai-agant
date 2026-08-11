# ERP Agent - 自然语言转 SQL（Artifact 模式）

将中文自然语言查询转换为 SQL 查询，由系统执行并呈现结果表。核心采用 **artifact（制品）模式**：Agent 只负责生成 SQL 制品，真正的数据查询由数据库执行，LLM 不亲自搬运数据——既节省 token，又避免大模型计算错误。

## 功能概述

- **自然语言转 SQL**：输入中文问题，自动生成 SQLite SQL 查询
- **Artifact 模式**：LLM 仅生成 SQL，数据库执行查询
- **10 个预设问题**：覆盖平均在职天数、部门统计、工资分析等场景
- **正确性校验**：通过独立 Python 参考实现验证 SQL 结果
- **离线自检**：无需 API 即可验证数据模型一致性

## 数据模型

**两张表：**

- `employees`：员工 ID、姓名、部门、级别（数字越大越高）、入职日期、离职日期（NULL = 在职）
- `salaries`：员工 ID、发薪日期（每月一条，`YYYY-MM-01`）、工资

数据由 `seed.py` 使用固定随机种子（42）生成，以「今天」为基准相对生成，**完全可复现**：
- 约 40 名员工跨 5 个部门/多级别
- 含若干已离职者
- 工资按「入职基准 + 每年固定涨薪额」生成
- 每人涨薪额互不相同（保证排名唯一）
- 特意制造一条拖欠工资记录（供问题 10 检测）

## 10 个预设问题

1. 平均每个员工在职多久
2. 每个部门有多少在职员工
3. 哪个部门平均级别最高
4. 每个部门今年/去年各新入职多少人
5. 前年 3 月到去年 5 月研发部平均工资
6. 去年研发部与销售部平均工资哪个高
7. 今年每个级别的员工平均工资
8. 入职一年内/一到两年/两到三年员工的最近一月平均工资
9. 去年到今年涨薪最大的 10 位员工
10. 有没有拖欠工资（某月在职却没发薪）

## 快速开始

### 1. 环境准备

确保已激活项目虚拟环境（在项目根目录）：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
```

### 2. 配置 LLM

在**项目根目录**的 `.env` 文件中配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选
```

### 3. 运行

```bash
# 进入项目目录
cd chapter5/erp-agent

# 离线自检（无需 API）
python demo.py gold

# 在线运行（需要 LLM 配置）
python demo.py run

# 单条查询
python demo.py ask "研发部现在有多少在职员工？"
```

## 使用方法

### 子命令

`demo.py` 提供 4 个子命令（不带子命令时等价于 `run`）：

| 子命令 | 需要 LLM | 作用 |
| --- | --- | --- |
| `run` | 需要 | 在线：Agent 生成 SQL → 执行 → 与参考实现比对 |
| `gold` | **不需要** | 离线：执行内置标准 SQL 跑 10 题并比对 |
| `ask` | 需要 | 单条自然语言查询 → SQL → 结果表 |
| `initdb` | 不需要 | 建表并把种子数据灌入 SQLite 文件 |

### 常用参数

```bash
# 只跑指定题号
python demo.py run --only 1,5,10

# 使用文件数据库而非内存库
python demo.py run --db erp.db

# 覆盖模型
python demo.py run --model claude-opus-4-8

# 导出结果 JSON
python demo.py run --output result.json
```

### 使用示例

```bash
# 离线自检（验证数据模型）
python demo.py gold

# 在线运行全部 10 题
python demo.py run

# 只跑第 2、3、6 题
python demo.py run --only 2,3,6

# 自定义查询
python demo.py ask "销售部今年平均工资是多少？"

# 初始化文件数据库
python demo.py initdb --db erp.db

# 使用文件数据库跑 gold 测试
python demo.py gold --db erp.db
```

## 项目结构

```
chapter5/erp-agent/
├── agent.py           # NL→SQL Agent（使用统一 LLM 客户端）
├── demo.py            # 命令行入口（run/gold/ask/initdb）
├── seed.py            # 可复现的种子数据生成
├── reference.py       # 独立 Python 参考实现（校验基准）
├── gold.py            # 手编标准 SQL（离线自检）
├── questions.py       # 10 个自然语言问题 + 提示
├── schema_postgres.sql # PostgreSQL 版 DDL（参考）
├── requirements.txt    # 项目依赖（无需额外依赖）
├── README.md          # 本文档
├── results/           # 结果输出目录
└── logs/              # 日志目录
```

## 配置说明

### LLM 配置（项目根目录 .env）

确保项目根目录的 `.env` 文件中已配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi
LLM_MODEL=kimi-k3
```

### 支持的 LLM 提供商

- Kimi（`kimi`）
- SiliconFlow（`siliconflow`）
- DeepSeek（`deepseek`）
- OpenAI（`openai`）
- 自定义（`custom`，需配置 BASE_URL）

## 正确性校验

- **`reference.py`**：独立的 Python 参考实现，不走 SQL，直接在种子数据上计算
- **`gold.py`**：人工编写的 10 条标准 SQL（SQLite 方言）
- **比对方式**：按「多重集合 + 数值容差」比对 SQL 结果与参考答案

最近运行结果：离线 `gold` 通过率 **10/10**；在线 `run` 稳定通过率 **10/10**。

## 故障排除

### LLM 调用失败

```
错误：无法导入 LLM 客户端
```

**解决方案**：
1. 确保项目根目录存在 `llm/client.py` 模块
2. 确保项目根目录的 `.env` 文件已配置 `API_KEY`

### 导入错误

```
ModuleNotFoundError: No module named 'llm'
```

**解决方案**：
1. 从项目根目录运行：`cd /home/jackluo/my/ai-agent/ai-agant`
2. 激活虚拟环境：`source .venv/bin/activate`
3. 运行：`python chapter5/erp-agent/demo.py gold`

### SQL 执行出错

**解决方案**：
1. 检查生成的 SQL 是否符合 SQLite 语法
2. 尝试更强的模型（`--model` 参数）
3. 查看详细错误信息

## 技术要点

### Artifact 模式

- LLM 只生成 SQL 制品，不搬运数据
- 数据库执行查询，避免 LLM 计算错误
- 节省 token，大结果集也能秒回

### 提示词设计

- 包含 schema 级提示（期望列/顺序、业务规则）
- 禁止硬编码年份（使用 `strftime(...,'now',...)` 推导）
- 复杂问题提供 SQL 结构模板

### 日期函数（SQLite）

| 功能 | SQLite | PostgreSQL |
| --- | --- | --- |
| 今年 | `strftime('%Y','now')` | `EXTRACT(YEAR FROM now())` |
| 去年 | `strftime('%Y','now','-1 year')` | `now() - interval '1 year'` |
| 日期差 | `julianday(date1) - julianday(date2)` | `AGE(date1, date2)` |
| 今天 | `date('now')` | `CURRENT_DATE` |

## 说明

- 优先使用 `python demo.py gold` 进行离线测试（无需 API）
- 问题 8、10 较复杂，提示中包含推荐的 SQL 结构模板
- `temperature=0` 保证输出稳定，但 LLM 非严格确定性
