"""基于真实 Playwright 的 Computer Use 注册表单操作面。"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from models import FieldSpec


class RecoverableFillError(RuntimeError):
    """单个字段的可恢复填写失败：可上报给 Phone Agent 而不必中断整通电话。"""


class RegistrationBrowser:
    """持有一个真实的 Chromium 浏览器/上下文/页面，并暴露表单操作。

    发现阶段生成的选择器由元素自身推导，保持内部使用。
    表单值永远不会出现在截图或轨迹文件中。
    """

    def __init__(self, url: str, *, headless: bool = False, submit: bool = False):
        self.url = url
        self.headless = headless
        self.submit_enabled = submit
        self._playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.closed = False

    async def open(self) -> None:
        """启动 Chromium 并打开目标页面。"""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        await self.page.goto(self.url, wait_until="domcontentloaded", timeout=60_000)

    async def discover_fields(self) -> List[FieldSpec]:
        """枚举页面上全部可填写控件，生成 FieldSpec 列表。"""
        if self.page is None:
            raise RuntimeError("浏览器尚未打开")
        raw = await self.page.locator(
            "input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled])"
        ).evaluate_all(
            """els => els.map((el, i) => {
              const id = el.id || '';
              const explicit = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
              const wrapping = el.closest('label');
              const aria = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || '';
              const label = (explicit?.innerText || wrapping?.innerText || aria || el.placeholder || el.name || id || `field_${i}`).trim();
              const selector = ((el.type === 'radio' || el.type === 'checkbox') && el.name) ?
                `input[name="${CSS.escape(el.name)}"]` : id ? `#${CSS.escape(id)}` :
                (el.name ? `${el.tagName.toLowerCase()}[name="${CSS.escape(el.name)}"]` :
                 `${el.tagName.toLowerCase()}:nth-of-type(${i + 1})`);
              return {
                name: el.name || id || `field_${i}`,
                label,
                input_type: el.tagName === 'SELECT' ? 'select' : (el.type || el.tagName.toLowerCase()),
                required: !!el.required || el.getAttribute('aria-required') === 'true',
                selector,
                format_hint: el.title || el.placeholder || '',
                pattern: el.pattern || '',
                options: el.tagName === 'SELECT' ? [...el.options].map(o => o.text.trim()).filter(Boolean) :
                  ((el.type === 'radio' || el.type === 'checkbox') ? [el.value, label].filter(Boolean) : [])
              };
            })"""
        )
        # 同名单选按钮在逻辑上是同一个字段，合并其选项
        fields: List[FieldSpec] = []
        seen: set[str] = set()
        for item in raw:
            spec = FieldSpec.from_dict(item)
            if spec.name in seen:
                existing = next(f for f in fields if f.name == spec.name)
                existing.options = list(dict.fromkeys(existing.options + spec.options))
                continue
            seen.add(spec.name)
            fields.append(spec)
        return fields

    @property
    async def title(self) -> str:
        return await self.page.title() if self.page else ""

    async def fill(self, field: FieldSpec, value: str) -> None:
        """把一个值写入对应的页面控件（支持 select/checkbox/radio/文本）。"""
        if self.page is None:
            raise RuntimeError("浏览器尚未打开")
        from playwright.async_api import Error as PlaywrightError

        try:
            locator = self.page.locator(field.selector).first
            await locator.scroll_into_view_if_needed()
            kind = field.input_type.lower()
            # 下拉框：先按显示文本选择，失败再按值选择
            if kind == "select":
                try:
                    await locator.select_option(label=value)
                except PlaywrightError:
                    await locator.select_option(value=value)
            elif kind in {"checkbox", "radio"}:
                # 单选/复选组：按 value 或关联 label 文本匹配目标项
                group = self.page.locator(field.selector)
                wanted = value.strip().casefold()
                chosen = None
                for i in range(await group.count()):
                    item = group.nth(i)
                    raw_value = (await item.get_attribute("value") or "").strip()
                    item_id = await item.get_attribute("id")
                    label = ""
                    if item_id:
                        label_node = self.page.locator(f'label[for="{item_id}"]').first
                        if await label_node.count():
                            label = (await label_node.inner_text()).strip()
                    if wanted in {raw_value.casefold(), label.casefold()}:
                        chosen = item
                        break
                if chosen is None:
                    raise RecoverableFillError(
                        f"{field.name} 在页面上没有匹配的选项"
                    )
                await chosen.check()
            else:
                await locator.fill(value)
        except RecoverableFillError:
            raise
        except PlaywrightError as exc:
            # 错误消息不包含值本身或 Playwright 原始文本：二者都可能携带
            # 用户提供的表单数据，绝不能进入日志或轨迹文件。
            raise RecoverableFillError(
                f"浏览器无法填写 {field.name}：{type(exc).__name__}"
            ) from exc

    async def submit(self) -> bool:
        """点击提交按钮；未显式授权时直接返回 False，不产生副作用。"""
        if not self.submit_enabled:
            return False
        if self.page is None:
            raise RuntimeError("浏览器尚未打开")
        button = self.page.locator(
            'button[type="submit"], input[type="submit"], button:has-text("注册"), button:has-text("Register")'
        ).first
        if await button.count() == 0:
            raise RuntimeError("页面没有可识别的提交按钮")
        await button.click()
        await asyncio.sleep(1)
        return True

    async def close(self) -> None:
        """幂等关闭上下文/浏览器/Playwright 驱动。"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
        self.closed = True

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
