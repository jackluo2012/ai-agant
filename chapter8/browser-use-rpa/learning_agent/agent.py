"""
基于经验学习的学习代理，扩展 browser-use 功能。

本代理封装 browser-use 代理以捕获成功的工作流，
并高效回放它们，无需 LLM 调用。
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
import time
from pathlib import Path
import sys
import os

# 添加父目录到路径以导入 browser-use
sys.path.append(str(Path(__file__).parent.parent))

from browser_use import Agent, Browser
from browser_use.agent.views import AgentOutput, ActionResult
from browser_use.browser.views import BrowserStateSummary

from .workflow import (
    Workflow, WorkflowStep, ActionType, StatePredicate, PredicateType,
)
from .knowledge_base import KnowledgeBase
from .replay import WorkflowReplayer


logger = logging.getLogger(__name__)


class LearningAgent:
    """
    从经验中学习并可以回放学习工作流的代理。

    本代理：
    1. 尝试将任务匹配到学习的工作流
    2. 对于新任务回退到 browser-use 代理
    3. 将成功执行捕获为新工作流
    4. 通过构建知识库随时间改进
    """

    def __init__(self,
                 task: str,
                 llm: Any,
                 browser: Optional[Browser] = None,
                 knowledge_base_path: str = "./knowledge_base",
                 headless: bool = False,
                 validation_reset: Optional[Any] = None,
                 **agent_kwargs):
        """
        初始化学习代理。

        Args:
            task: 要执行的任务
            llm: 要使用的语言模型（browser-use 兼容）
            browser: 浏览器实例（可选）
            knowledge_base_path: 存储学习工作流的路径
            headless: 是否以无界面模式运行浏览器进行回放
            validation_reset: 在验证候选工作流之前重置目标
                沙盒的同步或异步回调。没有它，
                候选工作流将被审计但从未发布以供复用。
            **agent_kwargs: browser-use 代理的额外参数
        """
        self.task = task
        self.llm = llm
        self.browser = browser
        self.headless = headless
        self.validation_reset = validation_reset

        # 初始化知识库
        self.knowledge_base = KnowledgeBase(knowledge_base_path)

        # 初始化工作流回放器
        self.replayer = WorkflowReplayer(headless=headless)

        # 工作流捕获状态
        self.current_workflow: Optional[Workflow] = None
        self.is_learning = False
        self.captured_steps: List[Dict[str, Any]] = []

        # Browser-use 代理（延迟初始化）
        self._agent: Optional[Agent] = None
        self._agent_kwargs = agent_kwargs

        # 指标
        self.metrics = {
            "llm_calls": 0,
            "replay_used": False,
            "execution_time": 0,
            "success": False
        }
    
    @property
    def agent(self) -> Agent:
        """Lazy initialization of browser-use agent."""
        if self._agent is None:
            # Create agent with step callback for capturing
            self._agent = Agent(
                task=self.task,
                llm=self.llm,
                browser=self.browser,
                **self._agent_kwargs
            )
            
            # Store original step method
            self._original_step = self._agent.step
            
            # Monkey-patch the step method to capture actions
            self._agent.step = self._wrapped_step
        
        return self._agent
    
    async def _wrapped_step(self, step_info=None):
        """Wrapped step method that captures workflow information."""
        # Call original step
        await self._original_step(step_info)
        
        # Capture step information if learning
        if self.is_learning:
            await self._capture_step()
    
    async def _capture_step(self):
        """Capture the current step for workflow learning."""
        try:
            # Get the last action and result from agent state
            if self.agent.state.last_model_output and self.agent.state.last_result:
                model_output = self.agent.state.last_model_output
                results = self.agent.state.last_result
                
                # Get browser state for element information
                browser_state = await self.agent.browser_session.get_browser_state_summary()
                
                # Process each action in the step
                for i, (action, result) in enumerate(zip(model_output.action, results)):
                    if result and not result.error:
                        # Extract action details
                        action_data = self._extract_action_data(action, result, browser_state)
                        if action_data:
                            self.captured_steps.append(action_data)
                            logger.debug(f"Captured step: {action_data['type']}")
        
        except Exception as e:
            logger.error(f"Failed to capture step: {e}")
    
    def _extract_action_data(self, action: Any, result: ActionResult, browser_state: BrowserStateSummary) -> Optional[Dict[str, Any]]:
        """
        Extract action data for workflow capture.
        
        Args:
            action: The action object from browser-use
            result: The result of the action
            browser_state: Current browser state
        
        Returns:
            Dictionary containing action data, or None if extraction fails
        """
        try:
            # exclude_unset is essential: a plain model_dump() emits a key
            # for EVERY registered action (None for the unset ones), which
            # made the first branch match every action and drop it on
            # None.get(...). browser-use itself reads action names the same
            # way (see browser_use/agent/service.py).
            action_dict = action.model_dump(exclude_unset=True) if hasattr(action, 'model_dump') else {}

            # Determine action type
            action_type = None
            parameters = {}
            element_info = None

            # Parse different action types
            if 'go_to_url' in action_dict:
                action_type = ActionType.NAVIGATE
                parameters = {'url': action_dict['go_to_url'].get('url')}

            elif 'click_element_by_index' in action_dict:
                action_type = ActionType.CLICK
                click_data = action_dict['click_element_by_index']
                parameters = {
                    'while_holding_ctrl': click_data.get('while_holding_ctrl', False)
                }
                
                # Get element info from selector map
                index = click_data.get('index')
                if index and browser_state.dom_state.selector_map:
                    element_info = self._get_element_info(index, browser_state.dom_state.selector_map)
            
            elif 'input_text' in action_dict:
                action_type = ActionType.INPUT_TEXT
                input_data = action_dict['input_text']
                parameters = {
                    'text': input_data.get('text', ''),
                    'clear_existing': input_data.get('clear_existing', True)
                }
                
                # Get element info
                index = input_data.get('index')
                if index and browser_state.dom_state.selector_map:
                    element_info = self._get_element_info(index, browser_state.dom_state.selector_map)
            
            elif 'select_dropdown_option' in action_dict:
                action_type = ActionType.SELECT_OPTION
                select_data = action_dict['select_dropdown_option']
                parameters = {
                    'text': select_data.get('text', '')
                }
                
                index = select_data.get('index')
                if index and browser_state.dom_state.selector_map:
                    element_info = self._get_element_info(index, browser_state.dom_state.selector_map)
            
            elif 'scroll' in action_dict:
                action_type = ActionType.SCROLL
                scroll_data = action_dict['scroll']
                parameters = {
                    'down': scroll_data.get('down', True),
                    'num_pages': scroll_data.get('num_pages', 1)
                }
            
            elif 'upload_file_to_element' in action_dict:
                action_type = ActionType.UPLOAD_FILE
                upload_data = action_dict['upload_file_to_element']
                parameters = {
                    'path': upload_data.get('path', '')
                }
                
                index = upload_data.get('index')
                if index and browser_state.dom_state.selector_map:
                    element_info = self._get_element_info(index, browser_state.dom_state.selector_map)
            
            elif 'done' in action_dict:
                # Skip done action for workflow
                return None
            
            if action_type:
                return {
                    'type': action_type,
                    'parameters': parameters,
                    'element_info': element_info,
                    'url': browser_state.url
                }
        
        except Exception as e:
            logger.error(f"Failed to extract action data: {e}")
        
        return None
    
    def _get_element_info(self, index: int, selector_map: Dict) -> Optional[Dict[str, Any]]:
        """
        Get element information from selector map.
        
        Args:
            index: Element index
            selector_map: Browser-use selector map
        
        Returns:
            Dictionary containing element selectors and attributes
        """
        try:
            if index in selector_map:
                element = selector_map[index]
                
                # Extract stable selectors
                info = {
                    'xpath': getattr(element, 'xpath', None),
                    'attributes': {}
                }
                
                # Get important attributes
                if hasattr(element, 'attributes') and element.attributes:
                    for attr in ['id', 'name', 'class', 'type', 'role', 'aria-label', 'data-testid']:
                        if attr in element.attributes:
                            info['attributes'][attr] = element.attributes[attr]
                
                return info
        
        except Exception as e:
            logger.error(f"Failed to get element info: {e}")
        
        return None
    
    async def run(self, max_steps: int = 100) -> Dict[str, Any]:
        """
        Run the learning agent to complete the task.
        
        Args:
            max_steps: Maximum steps for browser-use agent
        
        Returns:
            Dictionary containing execution results and metrics
        """
        start_time = time.time()
        
        try:
            # Check if we have a learned workflow for this task
            match = self.knowledge_base.find_workflow_for_task(self.task)
            
            if match and match.confidence > 0.6:
                # Use learned workflow
                logger.info(f"Found matching workflow: '{match.workflow.intent}' "
                          f"(confidence: {match.confidence:.2f})")
                logger.info(f"Match reason: {match.match_reason}")
                
                result = await self._run_with_replay(match.workflow)
                
                # A state-predicate failure means the page or API changed.
                # Remove this version from retrieval before falling back.
                if result['success']:
                    self.knowledge_base.update_workflow_metrics(
                        match.workflow.workflow_id,
                        success=True,
                        execution_time=result['execution_time'],
                        model_calls_saved=result['model_calls_saved']
                    )
                else:
                    reason = result.get('failed_predicate') or '; '.join(result.get('errors', []))
                    self.knowledge_base.invalidate_workflow(match.workflow.workflow_id, reason)
                
                self.metrics['replay_used'] = True
                self.metrics['success'] = result['success']
                
                # If replay failed, fall back to learning mode
                if not result['success']:
                    logger.warning("Replay failed, falling back to learning mode")
                    # The LLM loop is about to run, so this is no longer a
                    # replay run. Leaving the flag set makes the summary log and
                    # the demos report "0 LLM calls / Nx faster" for a run that
                    # actually made real LLM calls.
                    self.metrics['replay_used'] = False
                    result = await self._run_with_learning(max_steps)
            
            else:
                # No matching workflow, run in learning mode
                logger.info("No matching workflow found, running in learning mode")
                result = await self._run_with_learning(max_steps)
        
        finally:
            self.metrics['execution_time'] = time.time() - start_time
            
            # Log performance comparison
            if self.metrics['replay_used']:
                logger.info(f"Task completed with replay in {self.metrics['execution_time']:.2f}s")
                logger.info(f"Model calls saved: {result.get('model_calls_saved', 0)}")
            else:
                logger.info(f"Task completed with learning in {self.metrics['execution_time']:.2f}s")
                logger.info(f"LLM calls made: {self.metrics['llm_calls']}")
        
        return self.metrics
    
    async def _run_with_replay(self, workflow: Workflow) -> Dict[str, Any]:
        """
        使用学习的工作流运行任务。

        Args:
            workflow: 要回放的工作流

        Returns:
            执行结果
        """
        logger.info("回放学习的工作流...")

        # 如需要则从任务中提取参数
        parameters = self._extract_task_parameters(self.task, workflow)

        # 设置回放器
        await self.replayer.setup()

        try:
            # 回放工作流
            result = await self.replayer.replay_workflow(
                workflow,
                parameters=parameters
            )

            logger.info(f"回放完成：{result['steps_completed']}/{result['total_steps']} 步骤")

            return result

        finally:
            await self.replayer.cleanup()
    
    async def _run_with_learning(self, max_steps: int) -> Dict[str, Any]:
        """
        Run task with browser-use agent and capture workflow.
        
        Args:
            max_steps: Maximum steps for agent
        
        Returns:
            Execution results
        """
        logger.info("Running with browser-use agent (learning mode)...")
        
        # Enable learning mode
        self.is_learning = True
        self.captured_steps = []
        
        # Track LLM calls
        original_get_model_output = self.agent.get_model_output
        
        async def tracked_get_model_output(*args, **kwargs):
            self.metrics['llm_calls'] += 1
            return await original_get_model_output(*args, **kwargs)
        
        self.agent.get_model_output = tracked_get_model_output
        
        try:
            # Run the agent
            await self.agent.run(max_steps=max_steps)
            
            # Check if task was successful
            success = False
            if self.agent.state.last_result:
                for result in self.agent.state.last_result:
                    if result and hasattr(result, 'success') and result.success:
                        success = True
                        break
            
            self.metrics['success'] = success
            
            # If successful, save the workflow
            if success and self.captured_steps:
                await self._save_learned_workflow()
            
            return {
                'success': success,
                'steps_completed': len(self.captured_steps),
                'total_steps': len(self.captured_steps),
                'execution_time': self.metrics['execution_time'],
                'model_calls_saved': 0
            }
        
        finally:
            self.is_learning = False
    
    async def _save_learned_workflow(self):
        """Save the captured workflow to knowledge base."""
        try:
            # Create workflow from captured steps
            workflow = Workflow(
                workflow_id="",  # Will be generated
                intent=self.task,
                description=f"Learned workflow for: {self.task}",
                initial_url=self.captured_steps[0].get('url') if self.captured_steps else None
            )

            # Template the captured literals with the learning task's
            # parameters: captured steps store the exact values typed during
            # learning, and parameterize() only substitutes {placeholder}
            # tokens — without this step a replay would silently re-send the
            # learning run's recipient/subject/content.
            example_params = self._extract_task_parameters(self.task, workflow)
            workflow.example_parameters = dict(example_params)

            # Convert captured steps to workflow steps
            for step_data in self.captured_steps:
                parameters = dict(step_data['parameters'])
                for key, value in parameters.items():
                    if isinstance(value, str):
                        # Replace each captured literal with its {token}. Match
                        # longest values first so a shorter value that is a
                        # substring of a longer field (e.g. subject "Report"
                        # inside body "Report is ready") can't pre-empt it, and
                        # stage substitutions through unique sentinels so an
                        # already-inserted {token} is never re-scanned by a later
                        # parameter whose value happens to appear in the token
                        # text — the result no longer depends on iteration order.
                        sentinels = {}
                        for i, (param_key, param_value) in enumerate(sorted(
                            example_params.items(),
                            key=lambda kv: len(str(kv[1])),
                            reverse=True,
                        )):
                            pv = str(param_value)
                            if pv and pv in value:
                                sentinel = f"\x00{i}\x00"
                                sentinels[sentinel] = f"{{{param_key}}}"
                                value = value.replace(pv, sentinel)
                        for sentinel, token in sentinels.items():
                            value = value.replace(sentinel, token)
                        parameters[key] = value

                step = WorkflowStep(
                    action_type=step_data['type'],
                    parameters=parameters
                )

                # Add element info if available
                if step_data.get('element_info'):
                    element_info = step_data['element_info']
                    step.xpath = element_info.get('xpath')
                    step.element_attributes = element_info.get('attributes', {})

                workflow.add_step(step)

            # Derive conservative predicates from captured page state. A
            # production extractor can add richer text and state assertions.
            for step in workflow.steps:
                selector = f"xpath={step.xpath}" if step.xpath else step.css_selector
                if selector and step.action_type in {
                    ActionType.CLICK, ActionType.INPUT_TEXT,
                    ActionType.SELECT_OPTION, ActionType.UPLOAD_FILE,
                }:
                    step.preconditions.append(StatePredicate(
                        PredicateType.ELEMENT_VISIBLE,
                        expected=True,
                        selector=selector,
                        description="target element must be visible before action",
                    ))
                if step.action_type == ActionType.NAVIGATE and step.parameters.get('url'):
                    step.postconditions.append(StatePredicate(
                        PredicateType.URL_CONTAINS,
                        expected=step.parameters['url'],
                        description="navigation must reach the requested URL",
                    ))

            last_url = self.captured_steps[-1].get('url') if self.captured_steps else None
            if last_url:
                workflow.final_predicates.append(StatePredicate(
                    PredicateType.URL_CONTAINS,
                    expected=last_url,
                    description="workflow must finish on the observed final page",
                ))

            # First-run success creates only a candidate. Publication requires
            # an explicit environment reset and a full independent replay.
            self.knowledge_base.save_candidate(workflow)
            if self.validation_reset is None:
                logger.warning(
                    "Workflow remains candidate: no validation_reset callback was supplied"
                )
                return

            import inspect
            reset_result = self.validation_reset()
            if inspect.isawaitable(reset_result):
                await reset_result
            await self.replayer.setup()
            try:
                # Validate with the learned example parameters so the replay
                # substitutes the {placeholder} tokens back to concrete values.
                # Without this the validation run types the literal token text
                # (e.g. "{recipient}") into the page, so a correctly-learned
                # workflow fails validation and is never published — every later
                # replay then falls back to the LLM. (empty dict => no-op.)
                validation = await self.replayer.replay_workflow(
                    workflow, parameters=workflow.example_parameters
                )
            finally:
                await self.replayer.cleanup()
            if validation['success']:
                workflow.mark_validated()
                self.knowledge_base.publish_validated(workflow)
                logger.info("Validated and published workflow with %s steps", len(workflow.steps))
            else:
                logger.warning(
                    "Candidate replay failed and was not published: %s",
                    validation.get('failed_predicate') or validation.get('errors'),
                )
        
        except Exception as e:
            logger.error(f"Failed to save learned workflow: {e}")
    
    def _extract_task_parameters(self, task: str, workflow: Workflow) -> Dict[str, Any]:
        """
        Extract parameters from task description for workflow.
        
        Args:
            task: Task description
            workflow: Workflow that needs parameters
        
        Returns:
            Dictionary of extracted parameters
        """
        # This is a simplified parameter extraction
        # In production, you might use NLP or regex patterns
        parameters = {}
        
        # Example: Extract email addresses
        import re
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, task)
        if emails:
            parameters['recipient'] = emails[0]
        
        # Extract quoted text as subject or content
        quoted = re.findall(r'"([^"]*)"', task)
        if quoted:
            if 'subject' in task.lower() or '主题' in task.lower():
                parameters['subject'] = quoted[0]
                if len(quoted) > 1:
                    parameters['content'] = quoted[1]
            else:
                parameters['content'] = quoted[0]
        
        return parameters
    
    def run_sync(self, max_steps: int = 100) -> Dict[str, Any]:
        """
        Synchronous wrapper for run method.
        
        Args:
            max_steps: Maximum steps for browser-use agent
        
        Returns:
            Execution results
        """
        return asyncio.run(self.run(max_steps))
