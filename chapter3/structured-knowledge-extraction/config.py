"""
项目特定配置（非 LLM 配置）

LLM 配置已迁移到项目根目录的 .env 和 llm.client 模块。
本文件仅保留项目特定配置。
"""
import os

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# 缓存文件路径
SCHEMA_PATH = os.path.join(DATA_DIR, "schema.json")
EXTRACTED_CACHE_PATH = os.path.join(DATA_DIR, "extracted.jsonl")
ARCHETYPES_MODEL_PATH = os.path.join(DATA_DIR, "archetypes.json")

# 数据集路径
CASES_PATH = os.path.join(DATA_DIR, "cases.jsonl")

# 聚类参数（可调整）
CLUSTER_K_RANGE = range(2, 5)  # 聚类数量范围
CLUSTER_RANDOM_STATE = 42  # 聚类随机种子

# 抽取批大小
DISCOVERY_BATCH_SIZE = 12
