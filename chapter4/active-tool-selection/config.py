"""
主动工具选择代理配置

注意：LLM 配置在项目根目录的 .env 文件中统一管理。
本模块仅包含项目特定的配置参数。
"""

# 代理配置
AGENT_TEMPERATURE = 0.7  # LLM 温度参数
MAX_TOOL_REQUESTS = 5  # 工具发现的最大迭代次数

# 语义路由配置
SIMILARITY_THRESHOLD = 0.15  # 工具匹配的最小相似度分数
TOP_K_SERVERS = 3  # 要搜索的服务器数量
TOP_K_TOOLS = 5  # 每个服务器返回的工具数量
