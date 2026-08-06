# 感知工具 - 更新与变更

## 概述

将感知工具 MCP 服务器更新为使用 **100% 免费、开放的 API**，**无需任何 API 密钥**。这使得工具可以立即使用，无需任何设置或注册。

## 主要变更

### 1. **天气 API** - 用 Open-Meteo 替换 OpenWeather

**之前**: OpenWeather API（需要 API 密钥）
**现在**: [Open-Meteo](https://open-meteo.com/)（免费，无需 API 密钥）

**优势**:
- 无需注册或 API 密钥
- 自动对城市名称进行地理编码
- 来自国家气象服务的高质量天气数据
- 每小时分辨率，最多 16 天预报
- 提供 80 年的历史天气数据

**实现**:
- `get_weather(location, latitude=None, longitude=None)`
- 自动将位置名称地理编码为坐标
- 返回温度、湿度、风速、降水量和天气描述

---

### 2. **网络搜索** - 用 DuckDuckGo 替换 Google Custom Search

**之前**: Google Custom Search API（需要 API 密钥和 CSE ID）
**现在**: DuckDuckGo HTML 搜索（免费，无需 API 密钥）

**优势**:
- 无需注册或 API 密钥
- 注重隐私的搜索引擎
- 干净、无广告的结果
- 无使用限制

**实现**:
- `search_web(query, num_results=5, region="wt-wt")`
- 抓取 DuckDuckGo HTML 结果
- 返回每个结果的标题、URL 和摘要

---

### 3. **加密货币价格** - 新工具 ✨

**API**: [CoinGecko](https://www.coingecko.com/)（免费，无需 API 密钥）

**功能**:
- 实时加密货币价格
- 支持 15+ 种主要加密货币（BTC、ETH、SOL 等）
- 市值、24 小时交易量和价格变化数据
- 支持多种货币（USD、EUR、GBP 等）

**实现**:
- `get_crypto_price(symbol, vs_currency="usd")`
- 映射常见符号（btc → bitcoin，eth → ethereum）
- 返回全面的价格和市场数据

**示例**:
```python
result = await get_crypto_price("btc", "usd")
# 返回: BTC 价格、市值、24 小时交易量、24 小时变化
```

---

### 4. **位置搜索** - 新工具 ✨

**API**: [Nominatim (OpenStreetMap)](https://nominatim.openstreetmap.org/)（免费，无需 API 密钥）

**功能**:
- 对全球任何位置进行地理编码
- 搜索地标、城市、地址
- 详细的地址信息
- 国家过滤选项

**实现**:
- `search_location(query, limit=5, country_code=None)`
- 返回纬度、经度和详细地址
- 重要性排序以确保结果相关性

**示例**:
```python
result = await search_location("埃菲尔铁塔")
# 返回: 坐标、完整地址、位置类型
```

---

### 5. **兴趣点 (POI) 搜索** - 新工具 ✨

**API**: [Overpass API (OpenStreetMap)](https://overpass-api.de/)（免费，无需 API 密钥）

**功能**:
- 查找餐厅、咖啡馆、酒店、ATM、医院等
- 在指定半径内搜索
- 丰富的元数据（电话、网站、营业时间、菜系）
- 来自 OpenStreetMap 数据的全球覆盖

**实现**:
- `search_poi(query, latitude, longitude, radius=1000, limit=10)`
- 搜索设施、商店、旅游兴趣点
- 返回名称、类型、坐标和元数据

**示例**:
```python
result = await search_poi("restaurant", 48.8584, 2.2945, radius=500)
# 返回: 附近餐厅及其详细信息
```

---

## 已实现的免费 API

这些工具已经在使用免费 API:

1. **股票价格** - Yahoo Finance（免费，无需 API 密钥）
2. **货币转换** - ExchangeRate-API（免费，无需 API 密钥）
3. **Wikipedia** - Wikipedia API（免费，无需 API 密钥）
4. **ArXiv** - ArXiv API（免费，无需 API 密钥）
5. **Wayback Machine** - Internet Archive（免费，无需 API 密钥）

---

## 完整的免费工具列表

### 🔍 搜索与发现
- ✅ 网络搜索 (DuckDuckGo)
- ✅ 知识库搜索
- ✅ Wikipedia 搜索
- ✅ ArXiv 搜索
- ✅ 位置搜索 (OpenStreetMap)
- ✅ 兴趣点搜索 (OpenStreetMap)

### 🌐 公共数据
- ✅ 天气 (Open-Meteo)
- ✅ 股票价格 (Yahoo Finance)
- ✅ 加密货币价格 (CoinGecko)
- ✅ 货币转换 (ExchangeRate-API)

### 📄 内容处理
- ✅ 网页阅读器
- ✅ 文档阅读器 (PDF、DOCX、PPTX)
- ✅ 文件操作
- ✅ Grep 搜索

### 🕰️ 历史数据
- ✅ Wayback Machine

---

## 测试

所有新更新的工具已经过测试和验证：

```bash
# 测试原始工具
python quickstart.py

# 测试新工具
python test_new_tools.py
```

所有测试均通过，无需 API 密钥！

---

## 文档更新

- ✅ 更新 README.md 中新工具描述
- ✅ 更新 env.example 以反映免费 API
- ✅ 添加全面的参数文档
- ✅ 全文突出"无需 API 密钥"

---

## 这些变更的优势

1. **零设置** - 在 `pip install -r requirements.txt` 后立即可用
2. **零成本** - 所有 API 在合理使用范围内免费
3. **无需注册** - 无需注册或管理 API 密钥
4. **隐私保护** - DuckDuckGo 和 OpenStreetMap 不跟踪用户
5. **生产就绪** - API 稳定且维护良好
6. **全球覆盖** - 全球天气、地图和位置数据

---

## API 来源与链接

| 工具 | API 提供商 | 文档 |
|------|----------|------|
| 天气 | Open-Meteo | https://open-meteo.com/ |
| 网络搜索 | DuckDuckGo | https://duckduckgo.com/ |
| 加密货币价格 | CoinGecko | https://www.coingecko.com/en/api |
| 位置搜索 | Nominatim (OSM) | https://nominatim.openstreetmap.org/ |
| 兴趣点搜索 | Overpass API (OSM) | https://overpass-api.de/ |
| 股票价格 | Yahoo Finance | https://finance.yahoo.com/ |
| 货币 | ExchangeRate-API | https://www.exchangerate-api.com/ |
| Wikipedia | Wikipedia API | https://www.mediawiki.org/wiki/API |
| ArXiv | ArXiv API | https://arxiv.org/help/api |

---

## 致谢

特别感谢：
- Open-Meteo 提供免费、高质量的天气数据
- OpenStreetMap 社区维护全球地图数据
- CoinGecko 提供免费的加密货币市场数据
- DuckDuckGo 提供注重隐私的搜索

---

## 下一步

潜在的未来增强：
- 添加速率限制以尊重 API 使用策略
- 为频繁访问的数据实现缓存
- 添加更多加密货币交易所
- 支持反向地理编码
- 使用 OpenStreetMap 进行路线规划
