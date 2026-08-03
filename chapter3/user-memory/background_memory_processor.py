"""
后台记忆处理器 - 分析对话上下文并更新记忆
独立于主对话代理运行
"""

import json
import logging
import threading
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from config import Config, MemoryMode
from memory_manager import create_memory_manager, BaseMemoryManager
from conversation_history import ConversationHistory
from agent import UserMemoryAgent, UserMemoryConfig

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class MemoryUpdate:
    """表示记忆更新决策"""
    action: str  # 'add', 'update', 'delete', 'none'
    memory_id: Optional[str] = None
    content: Optional[str] = None
    reason: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class MemoryProcessorConfig:
    """后台记忆处理器配置"""
    conversation_interval: int = 1  # 在 N 轮对话后处理（默认：每轮）
    min_conversation_turns: int = 1  # 处理前的最小轮次
    context_window: int = 10  # 要分析的最近轮次数
    enable_auto_processing: bool = True
    temperature: float = 0.3  # 分析用的较低温度
    output_operations: bool = True  # 输出详细的记忆操作


class BackgroundMemoryProcessor:
    """
    后台处理器，分析对话并更新记忆
    独立于主对话流程运行
    """

    def __init__(self,
                 user_id: str,
                 provider: Optional[str] = None,
                 model: Optional[str] = None,
                 config: Optional[MemoryProcessorConfig] = None,
                 memory_mode: MemoryMode = MemoryMode.NOTES,
                 verbose: bool = True):
        """
        初始化后台记忆处理器

        Args:
            user_id: 唯一用户标识符
            provider: LLM 提供商（通过项目 .env 配置）
            model: 模型名称（通过项目 .env 配置）
            config: 处理器配置
            memory_mode: 记忆存储模式
            verbose: 启用详细日志
        """
        self.user_id = user_id
        self.verbose = verbose
        self.config = config or MemoryProcessorConfig()
        self.memory_mode = memory_mode
        self.provider = provider
        self.model = model

        # 初始化 UserMemoryAgent 用于分析
        agent_config = UserMemoryConfig(
            memory_mode=memory_mode,
            enable_memory_updates=True,  # 代理将使用其工具更新记忆
            enable_memory_search=True,  # 启用记忆搜索工具
            enable_conversation_history=False,
            save_trajectory=False  # 不保存后台处理的轨迹
        )
        self.analysis_agent = UserMemoryAgent(
            user_id=user_id,
            provider=provider,
            model=model,
            config=agent_config,
            verbose=self.verbose
        )

        # 初始化管理器
        self.memory_manager = create_memory_manager(user_id, memory_mode)
        self.conversation_history = ConversationHistory(user_id)

        # 后台处理状态
        self.processing_thread = None
        self.stop_processing = False
        self.last_processed_timestamp = None
        self.processing_lock = threading.Lock()
        self.conversation_count = 0  # 跟踪对话轮次
        self.last_processed_count = 0  # 跟踪最后处理的对话计数
        self.processed_turn_ids = set()  # 跟踪哪些轮次已处理

        logger.info(f"后台记忆处理器已为用户 {user_id} 初始化")
    
    def analyze_conversation(self, conversation_context: List[Dict[str, str]]) -> List[MemoryUpdate]:
        """
        Analyze conversation context and determine memory updates
        
        Args:
            conversation_context: List of conversation messages
            
        Returns:
            List of memory updates to apply
        """
        if len(conversation_context) < self.config.min_conversation_turns * 2:
            return []
        
        try:
            # Use UserMemoryAgent to analyze the conversation
            if self.verbose:
                logger.info("Analyzing conversation using UserMemoryAgent...")
            
            # Format the conversation for the agent
            conversation_str = "\n".join([
                f"{msg['role'].upper()}: {msg['content']}"
                for msg in conversation_context
            ])
            
            # 为代理创建任务以分析和更新记忆
            task = f"""分析最近的对话并相应地更新我的记忆。
提取任何重要的事实、偏好或应该记住的信息。

最近对话：
{conversation_str}

请审查此对话并：
1. 将任何新的重要信息添加为记忆
2. 如果有新的或变更的信息，更新现有记忆
3. 删除不再准确的任何记忆

专注于提取对未来对话有用的事实信息。"""
            
            # Execute the task using the agent's tool system
            result = self.analysis_agent.execute_task(task)
            
            if self.verbose:
                logger.info(f"Memory update task completed: {result.get('success', False)}")
            
            # Since the agent directly updates memories via tools, we don't need to return updates
            # The memories are already updated in the memory manager
            # Return empty list as updates were applied directly
            return []
            
        except Exception as e:
            logger.error(f"Failed to analyze conversation: {e}")
            return []
    
    def apply_memory_updates(self, updates: List[MemoryUpdate]) -> Dict[str, Any]:
        """
        Apply memory updates to the memory manager
        
        Args:
            updates: List of memory updates to apply
            
        Returns:
            Summary of applied updates
        """
        results = {
            'added': 0,
            'updated': 0,
            'deleted': 0,
            'failed': 0,
            'details': []
        }
        
        for update in updates:
            try:
                if update.action == 'add' and update.content:
                    # Handle different memory modes
                    if self.memory_mode in [MemoryMode.NOTES, MemoryMode.ENHANCED_NOTES]:
                        memory_id = self.memory_manager.add_memory(
                            content=update.content,
                            session_id=f"background-{datetime.now().isoformat()}",
                            tags=update.tags
                        )
                    elif self.memory_mode == MemoryMode.JSON_CARDS:
                        # Parse content as JSON for JSON cards mode
                        try:
                            if isinstance(update.content, str):
                                content_dict = json.loads(update.content)
                            else:
                                content_dict = update.content
                        except:
                            # Fallback to simple parsing
                            parts = str(update.content).split(':')
                            if len(parts) >= 2:
                                content_dict = {
                                    'category': 'personal',
                                    'subcategory': 'info',
                                    'key': parts[0].strip().replace(' ', '_').lower(),
                                    'value': ':'.join(parts[1:]).strip()
                                }
                            else:
                                content_dict = {
                                    'category': 'general',
                                    'subcategory': 'notes',
                                    'key': f"note_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                                    'value': update.content
                                }
                        
                        memory_id = self.memory_manager.add_memory(
                            content=content_dict,
                            session_id=f"background-{datetime.now().isoformat()}"
                        )
                    elif self.memory_mode == MemoryMode.ADVANCED_JSON_CARDS:
                        # For advanced JSON cards, expect proper structure
                        try:
                            if isinstance(update.content, str):
                                content_dict = json.loads(update.content)
                            else:
                                content_dict = update.content
                        except:
                            # Skip if can't parse
                            results['failed'] += 1
                            continue
                        
                        # Extract card data from the nested structure
                        card_data = content_dict.get('card', {})
                        
                        memory_id = self.memory_manager.add_memory(
                            content=content_dict,
                            session_id=f"background-{datetime.now().isoformat()}",
                            backstory=update.reason or '',
                            person=card_data.get('person', 'User'),
                            relationship=card_data.get('relationship', 'primary account holder')
                        )
                    else:
                        memory_id = self.memory_manager.add_memory(
                            content=update.content,
                            session_id=f"background-{datetime.now().isoformat()}",
                            tags=update.tags
                        )
                    results['added'] += 1
                    
                    # Format content for display
                    if isinstance(update.content, dict):
                        # For JSON modes, show a summary
                        if self.memory_mode == MemoryMode.ADVANCED_JSON_CARDS:
                            card_key = update.content.get('card_key', 'unknown')
                            category = update.content.get('category', 'unknown')
                            display_content = f"{category}.{card_key}"
                        else:
                            display_content = json.dumps(update.content, ensure_ascii=False)[:100]
                    else:
                        display_content = str(update.content)[:50]
                    
                    results['details'].append(f"Added: {display_content}...")
                    
                    # Always print to console for demo purposes
                    print(f"  📝 [ADD] Memory: {display_content}")
                    
                    if self.verbose:
                        logger.info(f"Added memory: {display_content}")
                
                elif update.action == 'update' and update.memory_id and update.content:
                    # Handle different memory modes
                    if self.memory_mode in [MemoryMode.NOTES, MemoryMode.ENHANCED_NOTES]:
                        success = self.memory_manager.update_memory(
                            memory_id=update.memory_id,
                            content=update.content,
                            session_id=f"background-{datetime.now().isoformat()}",
                            tags=update.tags
                        )
                    elif self.memory_mode == MemoryMode.JSON_CARDS:
                        # Parse content for JSON cards mode
                        try:
                            if isinstance(update.content, str):
                                content_dict = json.loads(update.content)
                            else:
                                content_dict = update.content
                        except:
                            # Simple value update
                            content_dict = {'value': update.content}
                        
                        success = self.memory_manager.update_memory(
                            memory_id=update.memory_id,
                            content=content_dict,
                            session_id=f"background-{datetime.now().isoformat()}"
                        )
                    elif self.memory_mode == MemoryMode.ADVANCED_JSON_CARDS:
                        # For advanced JSON cards, expect proper structure
                        try:
                            if isinstance(update.content, str):
                                content_dict = json.loads(update.content)
                            else:
                                content_dict = update.content
                        except:
                            # Skip if can't parse
                            results['failed'] += 1
                            continue
                        
                        success = self.memory_manager.update_memory(
                            memory_id=update.memory_id,
                            content=content_dict,
                            session_id=f"background-{datetime.now().isoformat()}"
                        )
                    else:
                        success = self.memory_manager.update_memory(
                            memory_id=update.memory_id,
                            content=update.content,
                            session_id=f"background-{datetime.now().isoformat()}",
                            tags=update.tags
                        )
                    if success:
                        results['updated'] += 1
                        
                        # Format content for display
                        if isinstance(update.content, dict):
                            if self.memory_mode == MemoryMode.ADVANCED_JSON_CARDS:
                                card_key = update.content.get('card_key', 'unknown')
                                category = update.content.get('category', 'unknown')
                                display_content = f"{category}.{card_key}"
                            else:
                                display_content = json.dumps(update.content, ensure_ascii=False)[:100]
                        else:
                            display_content = str(update.content)[:50]
                        
                        results['details'].append(f"Updated {update.memory_id}: {display_content}...")
                        
                        # Always print to console for demo purposes
                        print(f"  ✏️  [UPDATE] Memory (ID: {update.memory_id[:8] if len(update.memory_id) > 8 else update.memory_id}): {display_content}")
                    else:
                        results['failed'] += 1
                    
                    if self.verbose:
                        if isinstance(update.content, dict):
                            display_content = json.dumps(update.content, ensure_ascii=False)[:100]
                        else:
                            display_content = str(update.content)[:50]
                        logger.info(f"Updated memory {update.memory_id}: {display_content}")
                
                elif update.action == 'delete' and update.memory_id:
                    self.memory_manager.delete_memory(update.memory_id)
                    results['deleted'] += 1
                    results['details'].append(f"Deleted: {update.memory_id}")
                    
                    # Always print to console for demo purposes
                    print(f"  🗑️  [DELETE] Memory ID: {update.memory_id}")
                    
                    if self.verbose:
                        logger.info(f"Deleted memory: {update.memory_id}")
                
            except Exception as e:
                logger.error(f"Failed to apply update {update.action}: {e}")
                results['failed'] += 1
        
        return results
    
    def process_recent_conversations(self) -> Dict[str, Any]:
        """
        Process recent conversations and update memories
        
        Returns:
            Processing results with list of operations
        """
        with self.processing_lock:
            # Mark the current conversations as accounted for up front.
            # Without this, an early return below leaves last_processed_count
            # stale, so should_process() stays True and the background loop
            # re-triggers every second forever.
            self.last_processed_count = self.conversation_count
            self.last_processed_timestamp = datetime.now()

            # Reload history from disk: the main agent writes turns through its
            # own ConversationHistory instance, so this instance's in-memory
            # list is stale unless we re-read the file.
            self.conversation_history.load_history()

            # Get recent conversation turns
            recent_turns = self.conversation_history.get_recent_turns(
                limit=self.config.context_window
            )

            if not recent_turns:
                return {
                    'message': 'No recent conversations to process',
                    'operations': [],
                    'summary': {'added': 0, 'updated': 0, 'deleted': 0}
                }

            # Filter out already processed turns
            unprocessed_turns = []
            for turn in recent_turns:
                # Create a unique ID for each turn
                turn_id = f"{turn.session_id}_{turn.turn_number}_{turn.timestamp}"
                if turn_id not in self.processed_turn_ids:
                    unprocessed_turns.append(turn)
                    self.processed_turn_ids.add(turn_id)

            # If all turns have been processed, nothing to do
            if not unprocessed_turns:
                return {
                    'message': 'No new conversations to process',
                    'operations': [],
                    'summary': {'added': 0, 'updated': 0, 'deleted': 0}
                }
            
            # Convert to conversation format
            conversation_context = []
            for turn in unprocessed_turns:
                conversation_context.append({
                    'role': 'user',
                    'content': turn.user_message
                })
                conversation_context.append({
                    'role': 'assistant',
                    'content': turn.assistant_message
                })
            
            # Analyze conversation - this now directly updates memories via agent tools
            # The agent will process the conversation and use its tools to update memories
            _ = self.analyze_conversation(conversation_context)
            
            # Get the tool call history from the agent to report what was done
            tool_calls = getattr(self.analysis_agent, 'tool_calls', [])
            
            # Create operations list from tool calls
            operations = []
            summary = {'added': 0, 'updated': 0, 'deleted': 0}
            
            for tool_call in tool_calls:
                if tool_call.tool_name == 'add_memory':
                    operations.append({
                        'action': 'add',
                        'content': tool_call.arguments.get('content'),
                        'result': tool_call.result
                    })
                    if tool_call.result and tool_call.result.get('success'):
                        summary['added'] += 1
                elif tool_call.tool_name == 'update_memory':
                    operations.append({
                        'action': 'update',
                        'memory_id': tool_call.arguments.get('memory_id'),
                        'content': tool_call.arguments.get('content'),
                        'result': tool_call.result
                    })
                    if tool_call.result and tool_call.result.get('success'):
                        summary['updated'] += 1
                elif tool_call.tool_name == 'delete_memory':
                    operations.append({
                        'action': 'delete',
                        'memory_id': tool_call.arguments.get('memory_id'),
                        'result': tool_call.result
                    })
                    if tool_call.result and tool_call.result.get('success'):
                        summary['deleted'] += 1
            
            # Clear tool calls for next run
            self.analysis_agent.tool_calls = []
            
            # Format final results
            final_results = {
                'analyzed_turns': len(unprocessed_turns),
                'operations': operations,
                'summary': summary,
                'details': operations  # Operations are the details
            }

            return final_results
    
    def should_process(self) -> bool:
        """
        Check if memory processing should be triggered based on conversation count
        
        Returns:
            True if processing should occur
        """
        if self.conversation_count == 0:
            return False
        
        # Check if we've reached the conversation interval
        conversations_since_last = self.conversation_count - self.last_processed_count
        should_process = conversations_since_last >= self.config.conversation_interval
        
        # Debug logging to understand the issue
        if should_process and self.verbose:
            logger.debug(f"Should process: conv_count={self.conversation_count}, last_processed={self.last_processed_count}, interval={self.config.conversation_interval}")
        
        return should_process
    
    def increment_conversation_count(self):
        """
        Increment the conversation counter
        """
        self.conversation_count += 1
        
        if self.verbose:
            logger.info(f"Conversation count: {self.conversation_count}, Last processed: {self.last_processed_count}")
    
    def _background_processing_loop(self):
        """
        Background loop for automatic memory processing based on conversation count
        """
        logger.info(f"Starting background memory processing (interval: every {self.config.conversation_interval} conversations)")
        
        while not self.stop_processing:
            try:
                # Check every second if we should process
                time.sleep(1)
                
                if self.stop_processing:
                    break
                
                # Check if we should process based on conversation count
                if self.should_process():
                    if self.verbose:
                        logger.info(f"Processing triggered: conversations={self.conversation_count}, last_processed={self.last_processed_count}")
                    
                    results = self.process_recent_conversations()
                    
                    if self.config.output_operations and results:
                        self._output_operations(results)
                    
                    if self.verbose:
                        logger.info(f"Background processing results: {results.get('summary')}")
                        logger.info(f"Updated last_processed_count to {self.last_processed_count}")
                
            except Exception as e:
                logger.error(f"Error in background processing: {e}")
        
        logger.info("Background memory processing stopped")
    
    def _output_operations(self, results: Dict[str, Any]):
        """
        Output memory operations in a formatted way
        
        Args:
            results: Processing results with operations
        """
        operations = results.get('operations', [])
        summary = results.get('summary', {})
        
        # Don't log anything if there's no actual conversation to process
        if results.get('message') in ['No recent conversations to process', 'No new conversations to process']:
            return
            
        if not operations:
            # Only log when there were conversations analyzed but no updates needed
            if results.get('analyzed_turns', 0) > 0:
                logger.info("📝 Memory Operations: None (no updates needed)")
            return
        
        logger.info(f"\n📝 Memory Operations ({len(operations)} total):")
        logger.info("-" * 50)
        
        for i, op in enumerate(operations, 1):
            icon = {
                'add': '➕',
                'update': '📝',
                'delete': '🗑️'
            }.get(op['action'], '❓')
            
            logger.info(f"{i}. {icon} {op['action'].upper()}")
            if op.get('content'):
                logger.info(f"   Content: {op['content']}")
            if op.get('memory_id'):
                logger.info(f"   Memory ID: {op['memory_id']}")
            if op.get('reason'):
                logger.info(f"   Reason: {op['reason']}")
            if op.get('tags'):
                logger.info(f"   Tags: {', '.join(op['tags'])}")
            logger.info("")
        
        logger.info(f"Summary: {summary.get('added', 0)} added, {summary.get('updated', 0)} updated, {summary.get('deleted', 0)} deleted")
        logger.info("-" * 50)
    
    def start_background_processing(self):
        """Start the background memory processing thread"""
        if self.processing_thread and self.processing_thread.is_alive():
            logger.warning("Background processing already running")
            return
        
        self.stop_processing = False
        # Clear processed turns when starting fresh
        self.processed_turn_ids.clear()
        self.processing_thread = threading.Thread(
            target=self._background_processing_loop,
            daemon=True
        )
        self.processing_thread.start()
        logger.info("Background memory processing started")
    
    def stop_background_processing(self):
        """Stop the background memory processing thread"""
        self.stop_processing = True
        if self.processing_thread:
            self.processing_thread.join(timeout=5)
        logger.info("Background memory processing stopped")
    
    def process_conversation_batch(self, conversation_contexts: List[List[Dict[str, str]]]) -> List[Dict[str, Any]]:
        """
        Process multiple conversation contexts in batch
        
        Args:
            conversation_contexts: List of conversation contexts
            
        Returns:
            List of processing results
        """
        results = []
        
        for context in conversation_contexts:
            updates = self.analyze_conversation(context)
            
            operations = []
            for update in updates:
                operation = {
                    'action': update.action,
                    'content': update.content,
                }
                if update.memory_id:
                    operation['memory_id'] = update.memory_id
                operations.append(operation)
            
            if updates:
                apply_result = self.apply_memory_updates(updates)
                result = {
                    'operations': operations,
                    'summary': {
                        'added': apply_result['added'],
                        'updated': apply_result['updated'],
                        'deleted': apply_result['deleted']
                    }
                }
            else:
                result = {
                    'message': 'No updates needed',
                    'operations': [],
                    'summary': {'added': 0, 'updated': 0, 'deleted': 0}
                }
            
            results.append(result)
        
        return results
