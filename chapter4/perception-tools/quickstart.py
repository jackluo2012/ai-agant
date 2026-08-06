"""
快速测试脚本，用于测试感知工具 MCP 服务器。
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from search_tools import search_web, download_file
from multimodal_tools import read_webpage
from filesystem_tools import read_file, grep_search
from public_data_tools import get_weather, search_wikipedia, convert_currency


logging.basicConfig(level=logging.INFO)


async def test_tools():
    """测试各种感知工具。"""

    print("\n" + "="*80)
    print("感知工具 MCP 服务器 - 快速测试")
    print("="*80)

    # 测试 1：网络搜索
    print("\n📝 测试 1：网络搜索")
    print("-" * 80)
    try:
        result = await search_web("Python 编程", num_results=3)
        data = json.loads(result.text)
        if data['success']:
            print(f"✅ 找到 {data['message']['count']} 个结果")
            if data['message']['results']:
                for idx, result_item in enumerate(data['message']['results'], 1):
                    print(f"\n[{idx}] {result_item['title']}")
                    print(f"    URL: {result_item['url']}")
                    if result_item.get('snippet'):
                        print(f"    摘要: {result_item['snippet']}")
        else:
            print(f"⚠️  搜索 API 未配置：{data['message']}")
    except Exception as e:
        print(f"❌ 错误：{e}")

    # 测试 2：Wikipedia 搜索
    print("\n📝 测试 2：Wikipedia 搜索")
    print("-" * 80)
    try:
        result = await search_wikipedia("人工智能", sentences=3)
        data = json.loads(result.text)
        if data['success']:
            print(f"✅ 文章：{data['message']['title']}")
            print(f"摘要：{data['message']['summary'][:200]}...")
    except Exception as e:
        print(f"❌ 错误：{e}")

    # 测试 3：货币转换
    print("\n📝 测试 3：货币转换")
    print("-" * 80)
    try:
        result = await convert_currency(100, "USD", "EUR")
        data = json.loads(result.text)
        if data['success']:
            converted = data['message']['converted_amount']
            print(f"✅ 100 USD = {converted:.2f} EUR")
    except Exception as e:
        print(f"❌ 错误：{e}")

    # 测试 4：天气
    print("\n📝 测试 4：天气信息")
    print("-" * 80)
    try:
        result = await get_weather("伦敦")
        data = json.loads(result.text)
        if data['success']:
            temp = data['message']['temperature']
            desc = data['message']['description']
            print(f"✅ 伦敦：{temp}°C - {desc}")
        else:
            print(f"⚠️  天气 API 未配置：{data['message']}")
    except Exception as e:
        print(f"❌ 错误：{e}")

    # 测试 5：网页读取
    print("\n📝 测试 5：网页读取")
    print("-" * 80)
    try:
        result = await read_webpage("https://www.example.com", extract_text=True)
        data = json.loads(result.text)
        if data['success']:
            title = data['message']['title']
            text_len = data['message'].get('text_length', 0)
            print(f"✅ 页面：{title}")
            print(f"文本长度：{text_len} 个字符")
    except Exception as e:
        print(f"❌ 错误：{e}")

    # 测试 6：文件操作
    print("\n📝 测试 6：文件操作（读取此脚本）")
    print("-" * 80)
    try:
        script_path = str(Path(__file__).resolve())
        result = await read_file(script_path, max_length=500)
        data = json.loads(result.text)
        if data['success']:
            size = data['message']['size_bytes']
            print(f"✅ 从 {Path(script_path).name} 读取了 {size} 字节")
    except Exception as e:
        print(f"❌ 错误：{e}")

    print("\n" + "="*80)
    print("快速测试完成")
    print("="*80)
    print("\nℹ️  注意：如果未配置 API 密钥，某些测试可能会失败。")
    print("   查看 env.example 并配置您的 .env 文件以获得完整功能。")
    print("\n")


if __name__ == "__main__":
    asyncio.run(test_tools())
