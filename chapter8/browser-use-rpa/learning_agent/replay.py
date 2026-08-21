"""
使用 Playwright 的工作流回放功能。

本模块通过 Playwright 直接控制浏览器提供可靠的学习工作流回放，
绕过对 LLM 调用的需求。
"""

import asyncio
import logging
from typing import Any, Dict, Optional
from playwright.async_api import Page, Browser, async_playwright, Locator
import time

from .workflow import Workflow, WorkflowStep, ActionType, StatePredicate, PredicateType


logger = logging.getLogger(__name__)


class PredicateFailure(RuntimeError):
    """当真实页面不再满足工作流断言时抛出。"""


class WorkflowReplayer:
    """
    使用 Playwright 回放学习的工作流以实现直接浏览器控制。

    本回放器：
    - 无需 LLM 调用执行工作流
    - 通过智能等待处理动态页面加载
    - 提供强大的错误恢复
    - 跟踪执行指标
    """

    def __init__(self, headless: bool = False):
        """
        初始化工作流回放器。

        Args:
            headless: 是否以无界面模式运行浏览器
        """
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.context = None
        self.playwright = None

    async def setup(self):
        """初始化 Playwright 和浏览器。"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        self.page = await self.context.new_page()

        # 设置默认超时
        self.page.set_default_timeout(30000)

        logger.info("工作流回放器已初始化")

    async def cleanup(self):
        """清理浏览器资源。"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def replay_workflow(self,
                             workflow: Workflow,
                             parameters: Optional[Dict[str, Any]] = None,
                             initial_url: Optional[str] = None,
                             validate_state: bool = True) -> Dict[str, Any]:
        """
        使用给定参数回放工作流。

        Args:
            workflow: 要回放的工作流
            parameters: 应用于工作流的参数
            initial_url: 起始 URL（如果未提供则使用工作流的 initial_url）
            validate_state: 是否验证状态谓词

        Returns:
            包含执行结果和指标的字典
        """
        start_time = time.time()
        results = {
            "success": False,
            "steps_completed": 0,
            "total_steps": len(workflow.steps),
            "errors": [],
            "execution_time": 0,
            "model_calls_saved": len(workflow.steps),  # 每步都需要 LLM 调用
            "failed_predicate": None,
            "fallback_required": False,
            "actions_executed": [],
            "validation_enabled": validate_state,
        }

        try:
            # 如果提供了参数则应用
            if parameters:
                workflow = self._parameterize_workflow(workflow, parameters)

            # 导航到初始 URL
            start_url = initial_url or workflow.initial_url
            if start_url:
                logger.info(f"导航到初始 URL：{start_url}")
                await self.page.goto(start_url, wait_until='domcontentloaded')
                await self.page.wait_for_load_state('networkidle', timeout=10000)

            # 执行每个步骤
            for i, step in enumerate(workflow.steps):
                logger.info(f"执行步骤 {i+1}/{len(workflow.steps)}: {step.action_type.value}")

                try:
                    if validate_state:
                        await self._check_predicates(step.preconditions, f"步骤 {i+1} 前置条件")
                    await self._execute_step(step)
                    results["actions_executed"].append(step.action_type.value)
                    if validate_state:
                        await self._check_predicates(step.postconditions, f"步骤 {i+1} 后置条件")
                    results["steps_completed"] += 1

                    # 动作之间的短暂延迟以保持稳定性
                    await asyncio.sleep(0.5)

                except Exception as e:
                    error_msg = f"步骤 {i+1} 失败: {str(e)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)

                    if isinstance(e, PredicateFailure):
                        results["failed_predicate"] = str(e)
                    # 状态不匹配使所有后续操作不安全。停止
                    # 而不是声称部分动作执行成功。
                    break

            if results["steps_completed"] == results["total_steps"]:
                if validate_state:
                    await self._check_predicates(workflow.final_predicates, "工作流最终谓词")
                results["success"] = True

        except Exception as e:
            logger.error(f"工作流回放失败：{e}")
            results["errors"].append(str(e))
            if isinstance(e, PredicateFailure):
                results["failed_predicate"] = str(e)

        finally:
            results["execution_time"] = time.time() - start_time
            results["fallback_required"] = not results["success"]
            logger.info(f"工作流回放完成，耗时 {results['execution_time']:.2f}秒")

        return results

    async def _check_predicates(self, predicates, location: str) -> None:
        """检查状态谓词。"""
        for predicate in predicates:
            # 浏览器动作通常在其 fetch/DOM 回调提交可见状态之前解析。
            # 简要轮询真实页面，而不是将竞争转变为
            # 虚假失败或固定睡眠。
            deadline = time.monotonic() + 2.0
            ok, actual = await self._evaluate_predicate(predicate)
            while not ok and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
                ok, actual = await self._evaluate_predicate(predicate)
            if not ok:
                description = predicate.description or predicate.predicate_type.value
                raise PredicateFailure(
                    f"{location} 失败: {description}; 期望={predicate.expected!r}, 实际={actual!r}"
                )

    async def _evaluate_predicate(self, predicate: StatePredicate):
        """评估状态谓词。"""
        if self.page is None:
            return False, "页面未初始化"
        if predicate.predicate_type == PredicateType.URL_CONTAINS:
            actual = self.page.url
            return str(predicate.expected) in actual, actual
        if predicate.predicate_type == PredicateType.ELEMENT_VISIBLE:
            if not predicate.selector:
                return False, "缺少选择器"
            locator = self.page.locator(predicate.selector)
            actual = await locator.count() > 0 and await locator.first.is_visible()
            return actual == bool(predicate.expected), actual
        if predicate.predicate_type == PredicateType.ELEMENT_TEXT_CONTAINS:
            if not predicate.selector:
                return False, "缺少选择器"
            locator = self.page.locator(predicate.selector).first
            if await locator.count() == 0:
                return False, "元素缺失"
            actual = await locator.inner_text()
            return str(predicate.expected) in actual, actual
        if predicate.predicate_type == PredicateType.ELEMENT_VALUE_EQUALS:
            if not predicate.selector:
                return False, "缺少选择器"
            locator = self.page.locator(predicate.selector).first
            if await locator.count() == 0:
                return False, "元素缺失"
            actual = await locator.input_value()
            return actual == str(predicate.expected), actual
        if predicate.predicate_type == PredicateType.PAGE_STATE_EQUALS:
            if not predicate.state_key:
                return False, "缺少 state_key"
            actual = await self.page.evaluate(
                "key => window.__agentState ? window.__agentState[key] : undefined",
                predicate.state_key,
            )
            return actual == predicate.expected, actual
        return False, f"不支持的谓词 {predicate.predicate_type}"

    async def _execute_step(self, step: WorkflowStep) -> None:
        """
        执行单个工作流步骤。

        Args:
            step: 要执行的步骤
        """
        # 如果指定则在动作前等待
        if step.wait_before > 0:
            await asyncio.sleep(step.wait_before)

        # 根据动作类型执行
        if step.action_type == ActionType.NAVIGATE:
            await self._execute_navigate(step)
        elif step.action_type == ActionType.CLICK:
            await self._execute_click(step)
        elif step.action_type == ActionType.INPUT_TEXT:
            await self._execute_input(step)
        elif step.action_type == ActionType.SELECT_OPTION:
            await self._execute_select(step)
        elif step.action_type == ActionType.SCROLL:
            await self._execute_scroll(step)
        elif step.action_type == ActionType.WAIT:
            await self._execute_wait(step)
        elif step.action_type == ActionType.SWITCH_TAB:
            await self._execute_switch_tab(step)
        elif step.action_type == ActionType.UPLOAD_FILE:
            await self._execute_upload(step)
        else:
            logger.warning(f"不支持的动作类型：{step.action_type}")

    async def _get_element(self, step: WorkflowStep) -> Locator:
        """
        使用稳定选择器和回退方法获取元素。

        Args:
            step: 包含选择器信息的步骤

        Returns:
            元素的 Playwright 定位器
        """
        locator = None

        # 首先尝试 XPath（最稳定）
        if step.xpath:
            try:
                locator = self.page.locator(f"xpath={step.xpath}")
                # 检查元素是否存在
                if await locator.count() > 0:
                    # 等待元素准备就绪
                    await locator.wait_for(state='visible', timeout=step.timeout * 1000)
                    return locator
            except Exception as e:
                logger.debug(f"XPath 定位器失败：{e}")

        # 尝试 CSS 选择器作为回退
        if step.css_selector:
            try:
                locator = self.page.locator(step.css_selector)
                if await locator.count() > 0:
                    await locator.wait_for(state='visible', timeout=step.timeout * 1000)
                    return locator
            except Exception as e:
                logger.debug(f"CSS 选择器失败：{e}")

        # 尝试从属性构建选择器
        if step.element_attributes:
            selector_parts = []

            # 如果有 ID 则使用
            if 'id' in step.element_attributes:
                return self.page.locator(f"#{step.element_attributes['id']}")

            # 构建属性选择器
            for attr, value in step.element_attributes.items():
                if attr in ['name', 'type', 'role', 'aria-label', 'data-testid']:
                    selector_parts.append(f"[{attr}='{value}']")

            if selector_parts:
                selector = ''.join(selector_parts)
                try:
                    locator = self.page.locator(selector)
                    if await locator.count() > 0:
                        await locator.wait_for(state='visible', timeout=step.timeout * 1000)
                        return locator
                except Exception as e:
                    logger.debug(f"属性选择器失败：{e}")

        raise Exception(f"无法定位元素：{step.description}")

    async def _execute_navigate(self, step: WorkflowStep) -> None:
        """执行导航动作。"""
        url = step.parameters.get('url', '')
        logger.debug(f"导航到：{url}")
        await self.page.goto(url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle', timeout=10000)

    async def _execute_click(self, step: WorkflowStep) -> None:
        """执行点击动作。"""
        element = await self._get_element(step)
        logger.debug(f"点击元素：{step.description}")
        await element.click()

    async def _execute_input(self, step: WorkflowStep) -> None:
        """执行输入文本动作。"""
        element = await self._get_element(step)
        text = step.parameters.get('text', '')
        clear_existing = step.parameters.get('clear_existing', True)

        logger.debug(f"输入文本：{text}")

        if clear_existing:
            await element.fill(text)
        else:
            await element.type(text)

    async def _execute_select(self, step: WorkflowStep) -> None:
        """执行选择下拉选项动作。"""
        element = await self._get_element(step)
        text = step.parameters.get('text', '')

        logger.debug(f"选择选项：{text}")
        await element.select_option(label=text)

    async def _execute_scroll(self, step: WorkflowStep) -> None:
        """执行滚动动作。"""
        down = step.parameters.get('down', True)
        num_pages = step.parameters.get('num_pages', 1)

        logger.debug(f"滚动 {num_pages} 页")

        for _ in range(num_pages):
            if down:
                await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
            else:
                await self.page.evaluate("window.scrollBy(0, -window.innerHeight)")
            await asyncio.sleep(0.3)

    async def _execute_wait(self, step: WorkflowStep) -> None:
        """执行等待动作。"""
        duration = step.parameters.get('duration', 1.0)
        logger.debug(f"等待 {duration} 秒")
        await asyncio.sleep(duration)

    async def _execute_switch_tab(self, step: WorkflowStep) -> None:
        """执行切换标签页动作。"""
        tab_index = step.parameters.get('tab_index', 0)
        pages = self.context.pages
        if 0 <= tab_index < len(pages):
            self.page = pages[tab_index]
            logger.debug(f"切换到标签页 {tab_index}")

    async def _execute_upload(self, step: WorkflowStep) -> None:
        """执行文件上传动作。"""
        element = await self._get_element(step)
        file_path = step.parameters.get('path', '')

        logger.debug(f"上传文件：{file_path}")
        await element.set_input_files(file_path)

    def _parameterize_workflow(self, workflow: Workflow, parameters: Dict[str, Any]) -> Workflow:
        """
        将参数应用于工作流。

        Args:
            workflow: 要参数化的工作流
            parameters: 参数字典

        Returns:
            参数化的工作流
        """
        # 创建工作流的深拷贝
        import copy
        param_workflow = copy.deepcopy(workflow)

        # 应用参数到每个步骤
        for step in param_workflow.steps:
            for key, value in step.parameters.items():
                if isinstance(value, str):
                    # 替换参数占位符
                    for param_key, param_value in parameters.items():
                        placeholder = f"{{{param_key}}}"
                        if placeholder in value:
                            step.parameters[key] = value.replace(placeholder, str(param_value))

        return param_workflow
