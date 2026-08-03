#!/usr/bin/env python3
"""
Quick start script for User Memory System with Separated Architecture
Demonstrates conversation-based memory processing
"""

import os
import sys
import time
from dotenv import load_dotenv
from conversational_agent import ConversationalAgent, ConversationConfig
from background_memory_processor import BackgroundMemoryProcessor, MemoryProcessorConfig
from config import Config, MemoryMode
from memory_manager import create_memory_manager
from memory_operation_formatter import display_memory_operations

# Load environment variables
load_dotenv()


def quickstart():
    """运行记忆系统快速演示"""
    print("\n" + "="*60)
    print("🚀 用户记忆系统 - 快速开始")
    print("   (基于对话的记忆处理)")
    print("="*60)

    # LLM 配置在项目根目录的 .env 中设置
    print("\n💡 提示：确保在项目根目录的 .env 中配置了 API_KEY")
    
    # Create directories
    Config.create_directories()
    
    # Setup demo user
    user_id = "quickstart_user"
    memory_mode = MemoryMode.NOTES
    
    print(f"\n📌 Setting up separated architecture:")
    print(f"   • User: {user_id}")
    print(f"   • Memory Mode: {memory_mode.value}")
    print(f"   • Processing: After each conversation round")
    
    # Initialize conversational agent
    print("\n🤖 Initializing conversational agent...")
    agent = ConversationalAgent(
        user_id=user_id,
        memory_mode=memory_mode,
        config=ConversationConfig(
            enable_memory_context=True,
            enable_conversation_history=True
        ),
        verbose=False
    )
    
    # Initialize background memory processor
    print("🧠 Initializing memory processor...")
    processor = BackgroundMemoryProcessor(
        user_id=user_id,
        memory_mode=memory_mode,
        config=MemoryProcessorConfig(
            conversation_interval=1,  # Process after each conversation
            min_conversation_turns=1,
            output_operations=True
        ),
        verbose=False
    )
    
    print("✅ System initialized\n")
    
    # 会话 1：介绍与学习
    print("="*60)
    print("会话 1：介绍与学习")
    print("="*60)

    intro_messages = [
        "你好！我叫张三，是一名软件工程师，热爱 Python 和机器学习。",
        "我目前正在做一个推荐系统项目，使用 PyTorch 框架。",
        "我喜欢 IDE 用暗色主题，写 Python 代码时总是使用类型提示。"
    ]
    
    for i, msg in enumerate(intro_messages, 1):
        print(f"\n[对话轮次 {i}]")
        print(f"👤 User: {msg}")
        
        # Have conversation
        response = agent.chat(msg)
        print(f"🤖 Assistant: {response[:150]}..." if len(response) > 150 else f"🤖 Assistant: {response}")
        
        # Trigger memory processing after each conversation
        processor.increment_conversation_count()
        
        print(f"\n📝 正在处理对话 {i} 的记忆...")
        results = processor.process_recent_conversations()
        
        # Display memory operations
        operations = results.get('operations', [])
        if operations:
            print("\n记忆操作：")
            for j, op in enumerate(operations, 1):
                icon = {'add': '➕', 'update': '📝', 'delete': '🗑️'}.get(op['action'], '❓')
                print(f"  {j}. {icon} {op['action'].upper()}: {op.get('content', '')[:80]}...")
        else:
            print("  ℹ️ 无需更新记忆")
        
        summary = results.get('summary', {})
        if any(summary.values()):
            print(f"  汇总：{summary.get('added', 0)} 条新增，{summary.get('updated', 0)} 条更新")
    
    # 显示当前记忆状态
    print("\n" + "="*40)
    print("💾 会话 1 后的记忆状态")
    print("="*40)
    memory_manager = create_memory_manager(user_id, memory_mode)
    print(memory_manager.get_context_string())

    # 会话 2：测试记忆召回和更新
    print("\n" + "="*60)
    print("会话 2：记忆召回与更新")
    print("="*60)

    # 开始新对话会话
    agent.reset_session()
    print("🔄 已开始新对话会话\n")

    recall_messages = [
        "你记得我的工作和偏好吗？",
        "其实我最近从 PyTorch 换到了 JAX，为了更好的性能。",
        "根据你对我的了解，能推荐一些适合我的推荐系统工具吗？"
    ]
    
    for i, msg in enumerate(recall_messages, 1):
        print(f"\n[对话轮次 {i}]")
        print(f"👤 User: {msg}")
        
        # Have conversation
        response = agent.chat(msg)
        
        # Show full response for memory recall questions
        if "remember" in msg.lower() or "recommend" in msg.lower():
            print(f"🤖 Assistant: {response}")
        else:
            print(f"🤖 Assistant: {response[:150]}..." if len(response) > 150 else f"🤖 Assistant: {response}")
        
        # Trigger memory processing
        processor.increment_conversation_count()
        
        print(f"\n📝 正在处理对话 {i} 的记忆...")
        results = processor.process_recent_conversations()
        
        # Display memory operations
        operations = results.get('operations', [])
        if operations:
            print("\n记忆操作：")
            for j, op in enumerate(operations, 1):
                icon = {'add': '➕', 'update': '📝', 'delete': '🗑️'}.get(op['action'], '❓')
                content = op.get('content', op.get('memory_id', 'N/A'))
                print(f"  {j}. {icon} {op['action'].upper()}: {content[:80]}...")
                if op.get('reason'):
                    print(f"     原因：{op['reason'][:80]}...")
        else:
            print("  ℹ️ 无需更新记忆")
        
        summary = results.get('summary', {})
        if any(summary.values()):
            print(f"  汇总：{summary.get('added', 0)} 条新增，{summary.get('updated', 0)} 条更新")
    
    # 最终记忆状态
    print("\n" + "="*40)
    print("💾 最终记忆状态")
    print("="*40)
    memory_manager = create_memory_manager(user_id, memory_mode)
    final_memory = memory_manager.get_context_string()
    print(final_memory if final_memory else "未存储记忆")

    # 总结
    print("\n" + "="*60)
    print("✨ 快速开始完成！")
    print("="*60)
    print("\n🎯 演示的关键功能：")
    print("  • 对话与记忆处理分离")
    print("  • 每轮对话后进行记忆操作")
    print("  • 清晰的添加/更新/删除操作列表")
    print("  • 跨会话的记忆持久化")

    print("\n📚 下一步：")
    print("  1. 交互模式：python main.py --mode interactive --user your_name")
    print("  2. 调整处理间隔：--conversation-interval 2（每 2 次对话处理一次）")
    print("  3. 手动处理：--background-processing False")
    print("  4. 尝试 JSON 卡片：--memory-mode json_cards")
    print("  5. 运行完整演示：python main.py --mode demo")


if __name__ == "__main__":
    quickstart()
