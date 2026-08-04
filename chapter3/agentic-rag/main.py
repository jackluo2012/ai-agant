"""Agentic RAG 系统主入口"""

import sys
import os
import json
import logging
import argparse
from typing import Optional

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from config import Config, KnowledgeBaseType
from agent import AgenticRAG
from chunking import DocumentIndexer


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def setup_environment():
    """设置环境并检查要求"""
    config = Config.from_env()

    # 检查知识库设置
    if config.knowledge_base.type == KnowledgeBaseType.LOCAL:
        # 检查本地检索流水线是否运行
        import requests
        try:
            response = requests.get(f"{config.knowledge_base.local_base_url}/health", timeout=30)
            if response.status_code != 200:
                logger.warning("本地检索流水线未响应")
                logger.info(f"请确保检索流水线运行于 {config.knowledge_base.local_base_url}")
                logger.info("运行: cd ../../chapter3/retrieval-pipeline && python main.py")
        except:
            logger.warning("无法连接到本地检索流水线")
            logger.info("将继续执行 - 搜索可能失败")

    elif config.knowledge_base.type == KnowledgeBaseType.DIFY:
        if not config.knowledge_base.dify_api_key:
            logger.warning("未设置 Dify API 密钥")
            logger.info("请设置 DIFY_API_KEY 环境变量")

    return True


def run_interactive_mode(agent: AgenticRAG, mode: str = "agentic"):
    """运行交互式查询模式"""
    kb = agent.config.knowledge_base
    active_top_k = kb.offline_top_k if kb.type == KnowledgeBaseType.OFFLINE else kb.local_top_k

    print(f"\n{'='*60}")
    print(f"Agentic RAG 系统 - {mode.capitalize()} 模式")
    print(f"详细日志: {'开启' if agent.config.agent.verbose else '关闭'} | 知识库: {kb.type.value} | Top-K: {active_top_k}")
    print(f"{'='*60}")
    print("输入 'quit' 或 'exit' 退出")
    print("输入 'clear' 清除对话历史")
    print("输入 'mode' 切换 agentic/non-agentic 模式")
    print(f"{'='*60}\n")

    current_mode = mode

    while True:
        try:
            user_input = input("\n[用户] > ").strip()

            if user_input.lower() in ['quit', 'exit']:
                print("\n再见！")
                break

            if user_input.lower() == 'clear':
                agent.clear_history()
                print("对话历史已清除。")
                continue

            if user_input.lower() == 'mode':
                current_mode = "non-agentic" if current_mode == "agentic" else "agentic"
                print(f"已切换到 {current_mode} 模式")
                continue

            if not user_input:
                continue

            # 处理查询
            print(f"\n[助手 ({current_mode})] > ", end="", flush=True)

            if current_mode == "agentic":
                response = agent.query(user_input, stream=True)
            else:
                response = agent.query_non_agentic(user_input, stream=True)

            # 处理流式响应
            if hasattr(response, '__iter__'):
                for chunk in response:
                    print(chunk, end="", flush=True)
                print()  # 响应后换行
            else:
                print(response)

        except KeyboardInterrupt:
            print("\n\n已中断。输入 'quit' 退出。")
        except Exception as e:
            logger.error(f"错误: {e}")
            print(f"\n处理查询时出错: {e}")


def run_batch_mode(agent: AgenticRAG, queries_file: str, output_file: str, mode: str = "agentic"):
    """运行批量查询"""
    try:
        with open(queries_file, 'r', encoding='utf-8') as f:
            queries = [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"读取查询文件错误: {e}")
        return

    results = []

    for i, query in enumerate(queries, 1):
        print(f"\n[{i}/{len(queries)}] 处理中: {query[:100]}...")

        try:
            if mode == "agentic":
                response = agent.query(query, stream=False)
            else:
                response = agent.query_non_agentic(query, stream=False)

            results.append({
                "query": query,
                "response": response,
                "mode": mode
            })

        except Exception as e:
            logger.error(f"处理查询错误: {e}")
            results.append({
                "query": query,
                "response": f"错误: {str(e)}",
                "mode": mode
            })

    # 保存结果
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到 {output_file}")
    except Exception as e:
        logger.error(f"保存结果错误: {e}")


def run_comparison_mode(agent: AgenticRAG, query: str):
    """运行两种模式并比较结果"""
    print(f"\n{'='*60}")
    print("对比模式 - 同时运行 Agentic 和 Non-Agentic")
    print(f"{'='*60}")
    print(f"查询: {query}")
    print(f"{'='*60}")

    # 运行非 Agentic 模式
    print("\n[非 Agentic 模式]")
    print("-" * 40)
    non_agentic_response = agent.query_non_agentic(query, stream=False)
    print(non_agentic_response)

    # 清除历史以公平比较
    agent.clear_history()

    # 运行 Agentic 模式
    print("\n[Agentic 模式]")
    print("-" * 40)
    agentic_response = agent.query(query, stream=False)
    print(agentic_response)

    print(f"\n{'='*60}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="智能体化 RAG 系统：对比『智能体化（多轮迭代检索）』与『非智能体化（单次检索）』两种范式。",
        epilog=(
            "示例:\n"
            "  python main.py --kb-type offline --query \"醉酒过失致人重伤且有盗窃前科如何量刑\"\n"
            "  python main.py --query \"故意杀人罪判几年\" --mode compare --kb-type offline\n"
            "  python compare_offline.py   # 纯离线检索对比，无需 API 与外部服务\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # 模式选择
    parser.add_argument("--mode", choices=["agentic", "non-agentic", "compare"],
                        default="agentic",
                        help="查询模式：agentic=智能体化多轮检索 / non-agentic=单次检索 / compare=同题对比（默认：agentic）")

    # 查询选项
    parser.add_argument("--query", type=str, help="单条查询问题；不指定则进入交互模式")
    parser.add_argument("--batch", type=str, help="批量查询文件路径（每行一个问题）")
    parser.add_argument("--output", type=str, default="results.json",
                        help="批量结果的输出文件路径（默认：results.json）")

    # 配置选项
    parser.add_argument("--kb-type", choices=["offline", "local", "dify"],
                        help="知识库后端：offline=内置离线 BM25（无需服务/无需 API）/ local=检索流水线服务 / dify=Dify API")
    parser.add_argument("--corpus", type=str,
                        help="离线后端的法律语料目录（仅 --kb-type offline 生效，默认：laws）")
    parser.add_argument("--top-k", type=int, dest="top_k",
                        help="检索深度：每次检索返回的分块数量（默认：offline=5，local=3）")
    parser.add_argument("--verbose", action="store_true", help="输出详细的 Agent 推理轨迹")
    parser.add_argument("--no-verbose", action="store_true", help="关闭详细日志输出")

    # 索引选项
    parser.add_argument("--index", type=str, help="待索引的文件或目录路径")
    parser.add_argument("--chunk-size", type=int, default=2048, help="索引时的分块大小（字符数，默认：2048）")

    args = parser.parse_args()

    # 设置环境
    if not setup_environment():
        logger.warning("环境设置不完整，将继续执行...")

    # 加载或创建配置
    config = Config.from_env()

    # 默认开启详细模式
    config.agent.verbose = True

    # 用命令行参数覆盖配置
    if args.kb_type:
        config.knowledge_base.type = KnowledgeBaseType(args.kb_type)
    if args.corpus:
        config.knowledge_base.offline_corpus_path = args.corpus
    if args.top_k:
        # 同时设置离线与本地后端的检索深度，保持行为一致
        config.knowledge_base.offline_top_k = args.top_k
        config.knowledge_base.local_top_k = args.top_k

    # 处理详细模式
    if args.no_verbose:
        config.agent.verbose = False
    elif args.verbose:
        config.agent.verbose = True

    # 处理索引请求
    if args.index:
        print(f"\n{'='*60}")
        print("索引文档")
        print(f"{'='*60}")

        config.chunking.chunk_size = args.chunk_size
        indexer = DocumentIndexer(config.knowledge_base, config.chunking)

        from pathlib import Path
        path = Path(args.index)

        if path.is_file():
            result = indexer.index_file(str(path))
        elif path.is_dir():
            result = indexer.index_directory(str(path))
        else:
            print(f"路径未找到: {path}")
            return

        print(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"{'='*60}\n")

    # 创建 Agent
    try:
        agent = AgenticRAG(config)
    except Exception as e:
        logger.error(f"创建 Agent 失败: {e}")
        print(f"\n错误: {e}")
        print("请确保项目根目录的 .env 文件中配置了 API_KEY 和 LLM_PROVIDER")
        return

    # 处理不同执行模式
    if args.query and args.mode == "compare":
        # 单查询对比模式
        run_comparison_mode(agent, args.query)

    elif args.query:
        # 单查询模式
        kb = config.knowledge_base
        active_top_k = kb.offline_top_k if kb.type == KnowledgeBaseType.OFFLINE else kb.local_top_k
        print(f"\n[查询] {args.query}")
        print(f"[模式] {args.mode}")
        print(f"[知识库] {kb.type.value}")
        print(f"[详细日志] {'开启' if config.agent.verbose else '关闭'}")
        print(f"[Top-K] {active_top_k}")
        print("-" * 40)

        if args.mode == "agentic":
            response = agent.query(args.query, stream=False)
        else:
            response = agent.query_non_agentic(args.query, stream=False)

        print(response)

    elif args.batch:
        # 批量模式
        run_batch_mode(agent, args.batch, args.output, args.mode)

    else:
        # 交互模式（默认）
        run_interactive_mode(agent, args.mode)


if __name__ == "__main__":
    main()
