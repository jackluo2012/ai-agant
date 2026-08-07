"""
工具选择基准测试和离线评估。

提供一个小型标注基准测试（任务 -> 真实工具）和实用工具，用于*无需任何 API 调用*
即可量化本章的核心主张：当工具生态系统增长到数百个工具时，按需检索少数相关工具
可以在将所有工具模式转储到上下文的 token 成本大幅降低的同时，保持正确工具可达。

这里确定性地测量两件事：
  1. 检索召回@k — 真实工具是否在策略放入模型上下文的工具中？
  2. 上下文模式 tokens — 注入的工具模式消耗多少 token。

端到端准确率/延迟（模型是否实际*调用*了正确的工具）需要 API 密钥，
位于 demo_comparison.py 中。
"""

import sys
import os

# 路径处理：添加项目根目录和当前目录到 sys.path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from typing import List, Dict

from tool_knowledge_base import (
    ToolDefinition,
    ServerDefinition,
    create_tool_knowledge_base,
    get_all_tools,
    calculate_total_tokens,
)
from semantic_router import SemanticRouter


# 标注基准测试：每个任务都有一个（或少数几个可接受的）真实工具。
# 查询使用英文以匹配 TF-IDF 路由器使用的英文工具描述（参见 tool_knowledge_base.py）。
BENCHMARK_TASKS: List[Dict] = [
    {
        "name": "GitHub repo search",
        "task": "Search GitHub for popular Python machine learning repositories with more than 10000 stars",
        "gold_tools": ["github_search_repos"],
    },
    {
        "name": "Read config file",
        "task": "Read the contents of the local configuration file at /etc/app/config.json",
        "gold_tools": ["fs_read_file"],
    },
    {
        "name": "List directory",
        "task": "List all files and subdirectories under the /var/log directory",
        "gold_tools": ["fs_list_directory"],
    },
    {
        "name": "Summary statistics",
        "task": "Calculate the mean, median and standard deviation of last quarter's sales figures",
        "gold_tools": ["analytics_summarize"],
    },
    {
        "name": "Send email",
        "task": "Send the quarterly performance summary email to the team members",
        "gold_tools": ["comm_send_email"],
    },
    {
        "name": "Deploy to production",
        "task": "Deploy version 2.3.0 of the application to the production environment",
        "gold_tools": ["devops_deploy"],
    },
    {
        "name": "SQL query",
        "task": "Run a SQL query on the database to count the number of active users per region",
        "gold_tools": ["db_query"],
    },
    {
        "name": "Upload to cloud",
        "task": "Upload the local report file to the cloud storage bucket",
        "gold_tools": ["cloud_upload_storage"],
    },
    {
        "name": "Scrape prices",
        "task": "Scrape the prices of all products listed on the given web page",
        "gold_tools": ["web_scrape"],
    },
    {
        "name": "Monitor service",
        "task": "Get the current CPU and memory monitoring metrics for the staging service",
        "gold_tools": ["devops_monitor"],
    },
]


def make_distractor_servers(num_tools: int, start_index: int = 1,
                            tools_per_server: int = 5) -> List[ServerDefinition]:
    """
    生成合成*干扰*服务器/工具以扩充目录大小。

    这些是故意通用的"内部服务"操作。它们增加了真实的模式 token 并充当
    检索噪声，因此我们可以研究每个策略在生态系统增长到数百个工具时如何
    扩展——无需手动编写数百个真实工具。它们被清晰地命名为 ``svcN_opM``，
    以便不会有人将它们误认为真实目录。
    """
    servers: List[ServerDefinition] = []
    created = 0
    server_idx = start_index
    while created < num_tools:
        n = min(tools_per_server, num_tools - created)
        tools = []
        for j in range(1, n + 1):
            op = created + j
            tools.append(ToolDefinition(
                name=f"svc{server_idx}_op{j}",
                description=(
                    f"Auxiliary internal-service operation {op} for background "
                    f"housekeeping on internal resource group {server_idx}"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "resource_id": {"type": "string", "description": "Internal resource identifier"},
                        "options": {"type": "object", "description": "Operation options"},
                    },
                    "required": ["resource_id"],
                },
                server=f"internal_service_{server_idx}",
            ))
        servers.append(ServerDefinition(
            name=f"internal_service_{server_idx}",
            description=f"Internal auxiliary service {server_idx} for background housekeeping operations",
            tools=tools,
        ))
        created += n
        server_idx += 1
    return servers


def build_catalog(num_tools: int = 0) -> List[ServerDefinition]:
    """
    构建工具目录，可选择填充干扰工具。

    Args:
        num_tools: 目标工具总数。0（默认）保持真实目录不变。
            低于真实目录大小的值将被忽略（我们从不删除真实工具）；
            较大的值将用干扰工具填充。
    """
    servers = create_tool_knowledge_base()
    real_count = len(get_all_tools(servers))
    if num_tools and num_tools > real_count:
        servers = servers + make_distractor_servers(num_tools - real_count)
    return servers


def evaluate_offline(servers: List[ServerDefinition], top_k: int,
                     tasks: List[Dict] = None) -> Dict:
    """
    确定性地比较工具选择策略（无需 API 调用）。

    返回包含每个策略的聚合指标和每个任务检索详细信息的字典。
    两种策略可以直接离线比较：

      * ``all-tools``  — 注入每个工具模式。召回率构造为 1.0
        （真实工具始终存在）但 token 成本随目录增长。
      * ``retrieval``  — 仅注入 top-k 检索到的工具。召回率被测量；
        token 成本随目录增长保持大致平坦。

    （``active`` MCP-Zero 策略需要模型在循环中，因此仅在线基准测试中评估。）
    """
    tasks = tasks or BENCHMARK_TASKS
    router = SemanticRouter(servers)
    all_tools = get_all_tools(servers)
    all_tools_tokens = calculate_total_tokens(all_tools)

    per_task = []
    retrieval_hits = 0
    retrieval_tokens_sum = 0
    for t in tasks:
        retrieved = router.retrieve(t["task"], top_k)
        retrieved_names = [tool.name for tool in retrieved]
        hit = any(g in retrieved_names for g in t["gold_tools"])
        retrieval_hits += int(hit)
        retrieval_tokens_sum += calculate_total_tokens(retrieved)
        per_task.append({
            "name": t["name"],
            "gold_tools": t["gold_tools"],
            "retrieved": retrieved_names,
            "hit": hit,
        })

    n = len(tasks)
    return {
        "num_tools": len(all_tools),
        "top_k": top_k,
        "per_task": per_task,
        "strategies": {
            "all-tools": {
                "tools_in_context": len(all_tools),
                "avg_schema_tokens": all_tools_tokens,
                "recall": 1.0,
            },
            "retrieval": {
                "tools_in_context": top_k,
                "avg_schema_tokens": retrieval_tokens_sum / n,
                "recall": retrieval_hits / n,
            },
        },
    }
