"""
公开数据源工具：天气、股票、货币、Wikipedia、ArXiv、Wayback Machine
"""
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Union

import requests
from dotenv import load_dotenv
from mcp.types import TextContent
from pydantic import BaseModel, Field
import wikipedia

# 添加项目根目录到路径，用于导入 llm.client
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from base import ActionResponse


load_dotenv()


async def get_weather(
    location: str,
    latitude: float | None = None,
    longitude: float | None = None
) -> Union[str, TextContent]:
    """
    使用 Open-Meteo API 获取位置的当前天气信息。

    参数：
        location: 用于显示的城市名称
        latitude: 纬度坐标（如果未提供，将尝试对位置进行地理编码）
        longitude: 经度坐标（如果未提供，将尝试对位置进行地理编码）

    返回：
        包含天气数据的 TextContent
    """
    try:
        logging.info(f"🌤️ 正在获取天气：{location}")

        # 如果未提供坐标，尝试对位置进行地理编码
        if latitude is None or longitude is None:
            # 使用 Open-Meteo 的地理编码 API
            geocode_url = "https://geocoding-api.open-meteo.com/v1/search"
            geocode_params = {
                "name": location,
                "count": 1,
                "language": "en",
                "format": "json"
            }

            geocode_response = requests.get(geocode_url, params=geocode_params, timeout=10)
            geocode_response.raise_for_status()
            geocode_data = geocode_response.json()

            if not geocode_data.get("results"):
                raise ValueError(f"未找到位置：{location}")

            first_result = geocode_data["results"][0]
            latitude = first_result["latitude"]
            longitude = first_result["longitude"]
            location = first_result.get("name", location)
            country = first_result.get("country", "")
        else:
            country = ""

        # 从 Open-Meteo 获取天气数据
        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m",
            "timezone": "auto"
        }

        response = requests.get(weather_url, params=weather_params, timeout=10)
        response.raise_for_status()

        data = response.json()
        current = data["current"]

        # 将天气代码映射到描述
        # 基于 WMO 天气解释代码
        weather_codes = {
            0: "晴朗",
            1: "基本晴朗", 2: "部分多云", 3: "阴天",
            45: "有雾", 48: "沉积雾",
            51: "小雨", 53: "中雨", 55: "大雨",
            61: "小雪", 63: "中雪", 65: "大雪",
            77: "雪粒",
            80: "小阵雨", 81: "中阵雨", 82: "强阵雨",
            85: "小阵雪", 86: "大阵雪",
            95: "雷暴", 96: "雷暴并伴有小冰雹", 99: "雷暴并伴有大冰雹"
        }

        weather_code = current["weather_code"]
        description = weather_codes.get(weather_code, "未知")

        result = {
            "location": location,
            "country": country,
            "latitude": latitude,
            "longitude": longitude,
            "temperature": current["temperature_2m"],
            "feels_like": current["apparent_temperature"],
            "humidity": current["relative_humidity_2m"],
            "precipitation": current["precipitation"],
            "weather_code": weather_code,
            "description": description,
            "wind_speed": current["wind_speed_10m"],
            "wind_direction": current["wind_direction_10m"],
            "units": "metric",
            "timestamp": current["time"],
            "provider": "Open-Meteo"
        }

        logging.info(f"✅ 天气：{result['temperature']}°C - {result['description']}")

        action_response = ActionResponse(
            success=True,
            message=result,
            metadata={"location": location, "provider": "Open-Meteo", "api_key_required": False}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"天气查询失败：{str(e)}"
        logging.error(f"天气错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "weather_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def get_stock_price(
    symbol: str,
    interval: str = "1d"
) -> Union[str, TextContent]:
    """
    获取股票价格信息。

    参数：
        symbol: 股票代码（例如：AAPL、TSLA）
        interval: 数据间隔（1d、1h 等）

    返回：
        包含股票数据的 TextContent
    """
    try:
        logging.info(f"📈 正在获取股票价格：{symbol}")

        # 使用 Yahoo Finance API（免费，无需密钥）
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {
            "interval": interval,
            "range": "1d"
        }

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()

        if "chart" in data and "result" in data["chart"] and data["chart"]["result"]:
            quote = data["chart"]["result"][0]["meta"]

            result = {
                "symbol": symbol,
                "currency": quote.get("currency", "USD"),
                "current_price": quote.get("regularMarketPrice"),
                "previous_close": quote.get("previousClose"),
                "open": quote.get("regularMarketOpen"),
                "day_high": quote.get("regularMarketDayHigh"),
                "day_low": quote.get("regularMarketDayLow"),
                "volume": quote.get("regularMarketVolume"),
                "exchange": quote.get("exchangeName")
            }

            logging.info(f"✅ 股票价格：${result['current_price']}")
        else:
            raise ValueError(f"符号的响应无效：{symbol}")

        action_response = ActionResponse(
            success=True,
            message=result,
            metadata={"symbol": symbol}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"股票查询失败：{str(e)}"
        logging.error(f"股票错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "stock_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str
) -> Union[str, TextContent]:
    """
    货币之间转换。

    参数：
        amount: 转换金额
        from_currency: 源货币代码（例如：USD）
        to_currency: 目标货币代码（例如：EUR）

    返回：
        包含转换结果的 TextContent
    """
    try:
        logging.info(f"💱 正在转换 {amount} {from_currency} 到 {to_currency}")

        # 使用免费汇率 API
        url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        if to_currency not in data["rates"]:
            raise ValueError(f"未找到货币：{to_currency}")

        rate = data["rates"][to_currency]
        converted_amount = amount * rate

        result = {
            "amount": amount,
            "from_currency": from_currency,
            "to_currency": to_currency,
            "exchange_rate": rate,
            "converted_amount": converted_amount,
            "timestamp": data.get("date", datetime.now().isoformat())
        }

        logging.info(f"✅ {amount} {from_currency} = {converted_amount:.2f} {to_currency}")

        action_response = ActionResponse(
            success=True,
            message=result,
            metadata={"rate": rate}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"货币转换失败：{str(e)}"
        logging.error(f"货币错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "currency_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def search_wikipedia(
    query: str,
    language: str = "en",
    sentences: int = 5
) -> Union[str, TextContent]:
    """
    搜索 Wikipedia 并获取文章摘要。

    参数：
        query: 搜索查询
        language: Wikipedia 语言（en、zh 等）
        sentences: 摘要中的句子数量

    返回：
        包含 Wikipedia 文章的 TextContent
    """
    try:
        wikipedia.set_lang(language)

        logging.info(f"📚 正在搜索 Wikipedia：{query}")

        # 搜索页面
        search_results = wikipedia.search(query, results=3)

        if not search_results:
            raise ValueError(f"未找到 Wikipedia 文章：{query}")

        # 获取第一个结果的页面
        page = wikipedia.page(search_results[0], auto_suggest=False)

        summary = wikipedia.summary(search_results[0], sentences=sentences, auto_suggest=False)

        result = {
            "title": page.title,
            "url": page.url,
            "summary": summary,
            "language": language,
            "search_results": search_results
        }

        logging.info(f"✅ 找到 Wikipedia 文章：{page.title}")

        action_response = ActionResponse(
            success=True,
            message=result,
            metadata={"query": query, "language": language}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"Wikipedia 搜索失败：{str(e)}"
        logging.error(f"Wikipedia 错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "wikipedia_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def search_arxiv(
    query: str,
    max_results: int = 5,
    sort_by: str = "relevance"
) -> Union[str, TextContent]:
    """
    搜索 ArXiv 学术论文。

    参数：
        query: 搜索查询
        max_results: 最大结果数
        sort_by: 排序方式（relevance、lastUpdatedDate、submittedDate）

    返回：
        包含 ArXiv 论文的 TextContent
    """
    try:
        import arxiv

        logging.info(f"🔬 正在搜索 ArXiv：{query}")

        # 将 sort_by 映射到 arxiv.SortCriterion
        sort_map = {
            "relevance": arxiv.SortCriterion.Relevance,
            "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
            "submittedDate": arxiv.SortCriterion.SubmittedDate
        }

        sort_criterion = sort_map.get(sort_by, arxiv.SortCriterion.Relevance)

        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=sort_criterion
        )

        papers = []
        for result in search.results():
            papers.append({
                "title": result.title,
                "authors": [author.name for author in result.authors],
                "summary": result.summary[:500] + "...",
                "published": result.published.isoformat(),
                "url": result.entry_id,
                "pdf_url": result.pdf_url,
                "categories": result.categories
            })

        logging.info(f"✅ 找到 {len(papers)} 篇论文")

        action_response = ActionResponse(
            success=True,
            message={
                "query": query,
                "papers": papers,
                "count": len(papers)
            },
            metadata={"query": query, "max_results": max_results}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"ArXiv 搜索失败：{str(e)}"
        logging.error(f"ArXiv 错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "arxiv_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def search_wayback(
    url: str,
    year: int | None = None,
    limit: int = 10
) -> Union[str, TextContent]:
    """
    搜索 Wayback Machine 中 URL 的存档版本。

    参数：
        url: 搜索的 URL
        year: 可选的年份过滤器
        limit: 返回的最大快照数

    返回：
        包含存档快照的 TextContent
    """
    try:
        logging.info(f"🕰️ 正在搜索 Wayback Machine：{url}")

        # CDX API 端点
        cdx_url = "http://web.archive.org/cdx/search/cdx"
        params = {
            "url": url,
            "output": "json",
            "limit": limit,
            "fl": "timestamp,original,statuscode,mimetype"
        }

        if year:
            params["from"] = f"{year}0101"
            params["to"] = f"{year}1231"

        response = requests.get(cdx_url, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()

        # 第一行是标题
        if len(data) <= 1:
            raise ValueError(f"未找到存档快照：{url}")

        headers = data[0]
        snapshots = []

        for row in data[1:]:
            snapshot = dict(zip(headers, row))
            # 将时间戳转换为可读格式
            ts = snapshot["timestamp"]
            dt = datetime.strptime(ts, "%Y%m%d%H%M%S")

            snapshots.append({
                "timestamp": dt.isoformat(),
                "url": f"https://web.archive.org/web/{ts}/{snapshot['original']}",
                "status_code": snapshot.get("statuscode"),
                "mime_type": snapshot.get("mimetype")
            })

        logging.info(f"✅ 找到 {len(snapshots)} 个存档快照")

        action_response = ActionResponse(
            success=True,
            message={
                "url": url,
                "snapshots": snapshots,
                "count": len(snapshots)
            },
            metadata={"url": url, "year": year}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"Wayback Machine 搜索失败：{str(e)}"
        logging.error(f"Wayback 错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "wayback_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def get_crypto_price(
    symbol: str,
    vs_currency: str = "usd"
) -> Union[str, TextContent]:
    """
    使用 CoinGecko API 获取加密货币价格信息（免费，无需 API 密钥）。

    参数：
        symbol: 加密货币符号或 ID（例如：bitcoin、ethereum、btc、eth）
        vs_currency: 目标货币（usd、eur、gbp 等）

    返回：
        包含加密货币数据的 TextContent
    """
    try:
        logging.info(f"💰 正在获取加密货币价格：{symbol}")

        # CoinGecko 免费 API
        # 首先，尝试从符号获取硬币 ID
        symbol_lower = symbol.lower()

        # 将常用符号映射到 CoinGecko ID
        symbol_map = {
            "btc": "bitcoin",
            "eth": "ethereum",
            "usdt": "tether",
            "bnb": "binancecoin",
            "sol": "solana",
            "xrp": "ripple",
            "usdc": "usd-coin",
            "ada": "cardano",
            "doge": "dogecoin",
            "trx": "tron",
            "dot": "polkadot",
            "matic": "matic-network",
            "dai": "dai",
            "shib": "shiba-inu",
            "avax": "avalanche-2"
        }

        # 使用映射的 ID 或直接尝试符号
        coin_id = symbol_map.get(symbol_lower, symbol_lower)

        # 从 CoinGecko 获取价格数据
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": coin_id,
            "vs_currencies": vs_currency,
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
            "include_last_updated_at": "true"
        }

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()

        if not data or coin_id not in data:
            raise ValueError(f"未找到加密货币：{symbol}")

        coin_data = data[coin_id]

        result = {
            "symbol": symbol.upper(),
            "coin_id": coin_id,
            "currency": vs_currency.upper(),
            "current_price": coin_data.get(vs_currency),
            "market_cap": coin_data.get(f"{vs_currency}_market_cap"),
            "volume_24h": coin_data.get(f"{vs_currency}_24h_vol"),
            "price_change_24h_percent": coin_data.get(f"{vs_currency}_24h_change"),
            "last_updated": datetime.fromtimestamp(coin_data.get("last_updated_at", 0)).isoformat() if coin_data.get("last_updated_at") else None,
            "provider": "CoinGecko"
        }

        logging.info(f"✅ 加密货币价格：{result['current_price']} {vs_currency.upper()}")

        action_response = ActionResponse(
            success=True,
            message=result,
            metadata={"symbol": symbol, "provider": "CoinGecko", "api_key_required": False}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"加密货币价格查询失败：{str(e)}"
        logging.error(f"加密货币错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "crypto_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def search_location(
    query: str,
    limit: int = 5,
    country_code: str | None = None
) -> Union[str, TextContent]:
    """
    使用 Nominatim（OpenStreetMap）API 搜索位置（免费，无需 API 密钥）。

    参数：
        query: 位置查询（例如："埃菲尔铁塔"、"纽约"、"附近的咖啡店"）
        limit: 最大结果数（1-50）
        country_code: 可选的国家代码过滤器（例如："us"、"gb"、"fr"）

    返回：
        包含位置搜索结果的 TextContent
    """
    try:
        logging.info(f"📍 正在搜索位置：{query}")

        # Nominatim API（OpenStreetMap）
        url = "https://nominatim.openstreetmap.org/search"

        params = {
            "q": query,
            "format": "json",
            "limit": min(limit, 50),
            "addressdetails": 1,
            "extratags": 1
        }

        if country_code:
            params["countrycodes"] = country_code.lower()

        headers = {
            "User-Agent": "PerceptionToolsMCP/1.0"
        }

        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()

        if not data:
            raise ValueError(f"未找到位置：{query}")

        locations = []
        for item in data:
            address = item.get("address", {})

            locations.append({
                "display_name": item.get("display_name"),
                "latitude": float(item.get("lat")),
                "longitude": float(item.get("lon")),
                "type": item.get("type"),
                "category": item.get("class"),
                "address": {
                    "country": address.get("country"),
                    "country_code": address.get("country_code"),
                    "state": address.get("state"),
                    "city": address.get("city") or address.get("town") or address.get("village"),
                    "postcode": address.get("postcode"),
                    "road": address.get("road")
                },
                "importance": item.get("importance"),
                "osm_id": item.get("osm_id"),
                "osm_type": item.get("osm_type")
            })

        logging.info(f"✅ 找到 {len(locations)} 个位置")

        action_response = ActionResponse(
            success=True,
            message={
                "query": query,
                "locations": locations,
                "count": len(locations)
            },
            metadata={"provider": "Nominatim (OpenStreetMap)", "api_key_required": False}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"位置搜索失败：{str(e)}"
        logging.error(f"位置搜索错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "location_search_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )


async def search_poi(
    query: str,
    latitude: float,
    longitude: float,
    radius: int = 1000,
    limit: int = 10
) -> Union[str, TextContent]:
    """
    使用 Overpass API（OpenStreetMap）搜索位置附近的兴趣点。
    免费，无需 API 密钥。

    参数：
        query: 兴趣点类型（例如："restaurant"、"cafe"、"hospital"、"atm"、"hotel"）
        latitude: 中心纬度
        longitude: 中心经度
        radius: 搜索半径（米，默认：1000）
        limit: 最大结果数（默认：10）

    返回：
        包含兴趣点搜索结果的 TextContent
    """
    try:
        logging.info(f"🔍 正在搜索兴趣点：{query} 附近（{latitude}, {longitude}）")

        # Overpass API 查询
        # 搜索设施、商店、旅游等
        overpass_query = f"""
        [out:json][timeout:10];
        (
          node["amenity"~"{query}",i](around:{radius},{latitude},{longitude});
          node["shop"~"{query}",i](around:{radius},{latitude},{longitude});
          node["tourism"~"{query}",i](around:{radius},{latitude},{longitude});
          node["name"~"{query}",i](around:{radius},{latitude},{longitude});
        );
        out body {limit};
        """

        url = "https://overpass-api.de/api/interpreter"

        response = requests.post(url, data={"data": overpass_query}, timeout=30)
        response.raise_for_status()

        data = response.json()

        elements = data.get("elements", [])

        if not elements:
            raise ValueError(f"在指定位置附近未找到 '{query}' 的兴趣点")

        pois = []
        for element in elements[:limit]:
            tags = element.get("tags", {})

            pois.append({
                "name": tags.get("name", "未命名"),
                "type": tags.get("amenity") or tags.get("shop") or tags.get("tourism") or "unknown",
                "latitude": element.get("lat"),
                "longitude": element.get("lon"),
                "address": tags.get("addr:street"),
                "city": tags.get("addr:city"),
                "postcode": tags.get("addr:postcode"),
                "phone": tags.get("phone"),
                "website": tags.get("website"),
                "opening_hours": tags.get("opening_hours"),
                "cuisine": tags.get("cuisine"),
                "osm_id": element.get("id"),
                "osm_type": element.get("type")
            })

        logging.info(f"✅ 找到 {len(pois)} 个兴趣点")

        action_response = ActionResponse(
            success=True,
            message={
                "query": query,
                "center": {"latitude": latitude, "longitude": longitude},
                "radius_meters": radius,
                "pois": pois,
                "count": len(pois)
            },
            metadata={"provider": "Overpass API (OpenStreetMap)", "api_key_required": False}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )

    except Exception as e:
        error_msg = f"兴趣点搜索失败：{str(e)}"
        logging.error(f"兴趣点搜索错误：{traceback.format_exc()}")

        action_response = ActionResponse(
            success=False,
            message=error_msg,
            metadata={"error_type": "poi_search_error"}
        )

        return TextContent(
            type="text",
            text=json.dumps(action_response.model_dump(), ensure_ascii=False)
        )
