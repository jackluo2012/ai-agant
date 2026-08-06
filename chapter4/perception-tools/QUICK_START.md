# 快速开始指南 - 感知工具

## 🚀 无需设置！

所有工具立即可用，**无需任何 API 密钥**。

## 安装

```bash
cd /home/jackluo/my/ai-agent/ai-agant/chapter4/perception-tools
pip install -r requirements.txt
```

## 运行测试

```bash
# 测试原始工具
python quickstart.py

# 测试新的加密货币/位置/POI 工具
python test_new_tools.py
```

## 使用示例

### 1. 加密货币价格 💰

```python
from public_data_tools import get_crypto_price

# 获取比特币价格（美元）
result = await get_crypto_price("btc", "usd")

# 获取以太坊价格（欧元）
result = await get_crypto_price("eth", "eur")

# 支持: btc, eth, sol, ada, doge, bnb, xrp, usdt, usdc 等
```

### 2. 位置搜索 📍

```python
from public_data_tools import search_location

# 搜索任意位置
result = await search_location("埃菲尔铁塔", limit=5)

# 按国家过滤
result = await search_location("巴黎", country_code="fr")

# 搜索商家
result = await search_location("西雅图的星巴克")
```

### 3. 兴趣点搜索 🗺️

```python
from public_data_tools import search_poi

# 在某个位置附近找餐厅
result = await search_poi(
    query="restaurant",
    latitude=48.8584,
    longitude=2.2945,
    radius=500,  # 米
    limit=10
)

# 找咖啡馆
result = await search_poi("cafe", 37.7749, -122.4194, radius=1000)

# 找酒店、医院、ATM 等
result = await search_poi("hotel", lat, lon)
```

### 4. 天气查询 ⛅

```python
from public_data_tools import get_weather

# 按城市名获取天气
result = await get_weather("北京")

# 按坐标获取天气
result = await get_weather("巴黎", latitude=48.8566, longitude=2.3522)
```

### 5. 网络搜索 🔍

```python
from search_tools import search_web

# 搜索网络
result = await search_web("Python 编程", num_results=5)

# 区域搜索
result = await search_web("新闻", region="cn-zh")
```

### 6. 股票价格 📈

```python
from public_data_tools import get_stock_price

# 获取股票价格
result = await get_stock_price("AAPL")
result = await get_stock_price("TSLA")
```

## 所有可用的免费 API

| 工具 | 用途 | 示例 |
|------|----------|---------|
| 🔍 **网络搜索** | 搜索互联网 | `search_web("AI 新闻")` |
| 🌤️ **天气** | 当前天气 | `get_weather("北京")` |
| 💰 **加密货币价格** | 加密货币数据 | `get_crypto_price("btc")` |
| 📈 **股票价格** | 股票市场数据 | `get_stock_price("GOOGL")` |
| 💱 **货币转换** | 汇率 | `convert_currency(100, "USD", "CNY")` |
| 📍 **位置搜索** | 查找地点 | `search_location("埃菲尔铁塔")` |
| 🗺️ **POI 搜索** | 查找附近地点 | `search_poi("restaurant", lat, lon)` |
| 📚 **Wikipedia** | 百科全书 | `search_wikipedia("AI")` |
| 🔬 **ArXiv** | 学术论文 | `search_arxiv("deep learning")` |
| 🕰️ **Wayback Machine** | 存档网页 | `search_wayback("example.com")` |

## 常见使用场景

### 旅行规划

```python
# 1. 查找城市
location = await search_location("法国巴黎")
lat, lon = location['latitude'], location['longitude']

# 2. 检查天气
weather = await get_weather("巴黎")

# 3. 找酒店
hotels = await search_poi("hotel", lat, lon, radius=2000)

# 4. 找餐厅
restaurants = await search_poi("restaurant", lat, lon, radius=1000)

# 5. 货币转换
cost = await convert_currency(100, "USD", "EUR")
```

### 投资研究

```python
# 1. 获取股票价格
stock = await get_stock_price("AAPL")

# 2. 获取加密货币价格
btc = await get_crypto_price("btc")
eth = await get_crypto_price("eth")

# 3. 检查汇率
rate = await convert_currency(1, "USD", "CNY")

# 4. 在 Wikipedia 上研究
info = await search_wikipedia("苹果公司")
```

### 内容研究

```python
# 1. 网络搜索
results = await search_web("气候变化 2024")

# 2. 学术论文
papers = await search_arxiv("climate change")

# 3. Wikipedia
wiki = await search_wikipedia("气候变化")

# 4. 历史数据
archive = await search_wayback("ipcc.ch", year=2020)
```

## 响应格式

所有工具返回标准化的 JSON 响应：

```json
{
  "success": true,
  "message": {
    // 工具特定数据
  },
  "metadata": {
    "provider": "API 名称",
    "api_key_required": false
  }
}
```

## 提示与最佳实践

1. **速率限制**: 请尊重免费 API - 不要过度请求
2. **缓存**: 尽可能缓存结果以减少 API 调用
3. **错误处理**: 始终检查响应中的 `success` 字段
4. **用户代理**: 工具使用适当的 User-Agent 头以符合 API 要求

## 需要帮助？

- 📖 查看 `README.md` 获取完整文档
- 🔄 查看 `CHANGES.md` 了解新功能
- 🧪 运行 `python test_new_tools.py` 验证一切正常

## API 来源

- [Open-Meteo](https://open-meteo.com/) - 天气数据
- [CoinGecko](https://www.coingecko.com/) - 加密货币价格
- [OpenStreetMap](https://www.openstreetmap.org/) - 地图和 POI 数据
- [DuckDuckGo](https://duckduckgo.com/) - 网络搜索
- [Yahoo Finance](https://finance.yahoo.com/) - 股票价格
- [ExchangeRate-API](https://www.exchangerate-api.com/) - 汇率
