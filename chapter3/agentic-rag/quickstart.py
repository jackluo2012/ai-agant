#!/usr/bin/env python3
"""Agentic RAG 系统快速入门脚本"""

import sys
import os
from pathlib import Path


def check_environment():
    """检查环境是否正确配置"""
    print("🔍 检查环境...")

    # 检查项目根目录的 .env 文件
    # 项目使用统一的 .env 配置，位于项目根目录
    project_root = Path(__file__).parent.parent.parent
    env_file = project_root / ".env"

    if not env_file.exists():
        print(f"❌ 未找到项目配置文件: {env_file}")
        print("   请在项目根目录创建 .env 文件并配置 API_KEY 等参数")
        print("   参考: ai-agant/.env.example")
        return False

    print(f"✅ 找到配置文件: {env_file}")

    # 检查是否设置了 API_KEY
    from dotenv import load_dotenv
    load_dotenv(env_file)

    if os.getenv("API_KEY"):
        print("✅ 已配置 API_KEY")
        return True
    else:
        print("⚠️  未设置 API_KEY")
        print("   请在 .env 文件中设置 API_KEY 参数")
        return False


def setup_demo_documents():
    """创建演示文档（如果不存在）"""
    print("\n📚 设置演示文档...")

    eval_dir = Path("evaluation")
    eval_dir.mkdir(exist_ok=True)

    # 检查文档是否已存在
    doc_file = eval_dir / "legal_documents.json"
    dataset_file = eval_dir / "legal_qa_dataset.json"

    if not doc_file.exists() or not dataset_file.exists():
        print("📄 生成法律文档和数据集...")
        os.chdir("evaluation")
        os.system("python dataset_builder.py")
        os.chdir("..")
        print("✅ 文档已生成")
    else:
        print("✅ 文档已存在")

    return doc_file, dataset_file


def check_retrieval_pipeline():
    """检查本地检索流水线是否运行"""
    print("\n🔌 检查检索流水线...")

    kb_type = os.getenv("KB_TYPE", "local")

    if kb_type == "local":
        import requests
        try:
            response = requests.get("http://localhost:4242/health", timeout=2)
            if response.status_code == 200:
                print("✅ 本地检索流水线正在运行")
                return True
        except:
            pass

        print("⚠️  本地检索流水线未运行")
        print("    请在另一个终端运行:")
        print("    cd ../../chapter3/retrieval-pipeline && python main.py")
        print("\n    或在 .env 中设置 KB_TYPE=dify 使用 Dify")
        return False
    else:
        print(f"✅ 使用 {kb_type} 知识库")
        return True


def run_demo():
    """运行交互式演示"""
    print("\n" + "="*60)
    print("🚀 启动 Agentic RAG 演示")
    print("="*60)

    print("\n可尝试的查询:")
    print("1. 故意杀人罪判几年？")
    print("2. 盗窃罪的立案标准是什么？")
    print("3. 醉酒驾驶如何处罚？")
    print("4. 张某持刀入室抢劫并造成他人重伤，应如何定罪量刑？")

    print("\n命令:")
    print("- 'mode' 切换 agentic/non-agentic 模式")
    print("- 'clear' 清除对话历史")
    print("- 'quit' 退出")

    print("\n启动交互模式...")
    print("-"*60)

    os.system("python main.py")


def run_comparison_demo():
    """运行 Agentic 与非 Agentic 模式对比"""
    print("\n" + "="*60)
    print("🔄 运行对比演示")
    print("="*60)

    queries = [
        "故意杀人罪判几年？",
        "张某因经济纠纷持刀闯入李某家中，刺伤李某致重伤并拿走5万元现金，应如何定罪？"
    ]

    for query in queries:
        print(f"\n📝 查询: {query}")
        os.system(f'python main.py --mode compare --query "{query}"')
        input("\n按回车继续...")


def main():
    """主函数"""
    print("🎯 Agentic RAG 系统 - 快速入门")
    print("="*60)

    # 检查环境
    if not check_environment():
        print("\n❌ 请先配置环境")
        sys.exit(1)

    # 设置演示文档
    doc_file, dataset_file = setup_demo_documents()

    # 检查检索流水线
    if not check_retrieval_pipeline():
        print("\n⚠️  警告: 检索流水线不可用")
        print("    系统可能无法正常工作")
        response = input("\n是否继续? (y/n): ")
        if response.lower() != 'y':
            sys.exit(0)

    # 菜单
    print("\n" + "="*60)
    print("📋 选择选项:")
    print("="*60)
    print("1. 交互式演示（与系统对话）")
    print("2. 对比演示（查看 Agentic vs 非 Agentic）")
    print("3. 运行完整评估")
    print("4. 退出")

    choice = input("\n你的选择 (1-4): ")

    if choice == "1":
        run_demo()
    elif choice == "2":
        run_comparison_demo()
    elif choice == "3":
        print("\n📊 运行完整评估...")
        os.chdir("evaluation")
        os.system("python evaluate.py")
        os.chdir("..")
    elif choice == "4":
        print("\n👋 再见！")
    else:
        print("\n❌ 无效选择")


if __name__ == "__main__":
    # 如有需要，安装依赖
    try:
        import requests
    except ImportError:
        print("📦 安装所需包...")
        os.system("pip install -r requirements.txt")
        print("✅ 包已安装")

    main()
