"""UI 测试执行引擎服务.

REF-02: 从 ``app/api/v1/ui_test_cases.py`` 提取的 Playwright 执行逻辑，包括：
- 健壮操作辅助函数（``_robust_*``）
- 步骤组展开 ``_expand_step_groups``
- 执行引擎 ``_execute_steps_with_playwright`` / ``_execute_with_retry``
- 公共入口 ``execute_ui_case``

SEC-06: upload/download 步骤通过 ``artifact_service.resolve_artifact_path`` 解析文件路径。
"""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.services.ui.artifact_service import resolve_artifact_path


# ---------------------------------------------------------------------------
# 健壮操作辅助函数：处理元素不可见、需要滚动、选择器脆弱等情况
# ---------------------------------------------------------------------------

def _extract_text_from_desc(desc: str) -> str | None:
    """从描述中提取目标文本，用于兜底定位.

    描述格式如 "点击 订单管理" / "输入 用户名 "testuser"" → 提取 "订单管理" / "用户名"
    """
    if not desc:
        return None
    # 去掉动作前缀（点击/输入/选择/按键/导航）
    for prefix in ("点击 ", "输入 ", "选择 ", "按键 ", "导航 "):
        if desc.startswith(prefix):
            rest = desc[len(prefix):]
            # 对于 input，rest 可能是 '用户名 "testuser"'，取引号前的部分
            if '"' in rest:
                rest = rest.split('"')[0].strip()
            rest = rest.strip()
            if rest and len(rest) <= 40:
                return rest
    return None


def _robust_click(page, selector: str, desc: str = "") -> None:
    """健壮点击：普通点击 → 滚动后点击 → 强制点击 → 文本强制点击 → JS点击."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    # 第一次尝试：普通点击
    try:
        page.click(selector, timeout=8000)
        return
    except PlaywrightTimeout:
        pass  # 继续尝试其他策略
    except Exception:
        pass

    # 第二次尝试：滚动到可视区域后点击
    try:
        locator = page.locator(selector).first
        locator.scroll_into_view_if_needed(timeout=3000)
        locator.click(timeout=5000)
        return
    except Exception:
        pass

    # 第三次尝试：强制点击（忽略可见性检查）
    try:
        page.click(selector, force=True, timeout=5000)
        return
    except Exception:
        pass

    # 第四次尝试：基于描述文本兜底定位（force=True 忽略可见性）
    text = _extract_text_from_desc(desc)
    if text:
        # 文本选择器 + force
        try:
            text_locator = page.locator(f"text={text}").first
            text_locator.click(force=True, timeout=5000)
            return
        except Exception:
            pass
        # get_by_text + force
        try:
            text_locator = page.get_by_text(text, exact=False).first
            text_locator.click(force=True, timeout=5000)
            return
        except Exception:
            pass
        # CSS 类文本匹配 + force（针对 menu-item 等组件）
        try:
            # 尝试用 contains 文本匹配常见菜单/按钮元素
            js_selector = (
                f"span:has-text('{text}'), a:has-text('{text}'), "
                f"div:has-text('{text}'), li:has-text('{text}'), "
                f"button:has-text('{text}')"
            )
            el_locator = page.locator(js_selector).first
            el_locator.click(force=True, timeout=5000)
            return
        except Exception:
            pass

    # 第五次尝试：JavaScript 直接 dispatch click 事件（终极兜底）
    try:
        page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (el) {
                    el.scrollIntoView();
                    el.click();
                    return true;
                }
                return false;
            }""",
            selector,
        )
        return
    except Exception:
        pass

    # JS + 文本兜底
    if text:
        try:
            page.evaluate(
                """(txt) => {
                    const elements = document.querySelectorAll('span, a, div, li, button');
                    for (const el of elements) {
                        if (el.textContent && el.textContent.trim() === txt) {
                            el.scrollIntoView();
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""",
                text,
            )
            return
        except Exception:
            pass

    # 所有策略都失败，抛出原始错误
    page.click(selector, timeout=8000)


def _robust_input(page, selector: str, value: str, desc: str = "") -> None:
    """健壮输入：普通输入 → 滚动后输入 → 强制输入 → 文本兜底定位."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    # 第一次尝试：普通 fill
    try:
        page.fill(selector, value, timeout=8000)
        return
    except PlaywrightTimeout:
        pass
    except Exception:
        pass

    # 第二次尝试：滚动后 fill
    try:
        locator = page.locator(selector).first
        locator.scroll_into_view_if_needed(timeout=3000)
        locator.fill(value, timeout=5000)
        return
    except Exception:
        pass

    # 第三次尝试：点击聚焦后用 keyboard 输入
    try:
        page.click(selector, force=True, timeout=5000)
        page.keyboard.type(value)
        return
    except Exception:
        pass

    # 第四次尝试：基于描述文本兜底
    text = _extract_text_from_desc(desc)
    if text:
        try:
            text_locator = page.locator(f"text={text}").first
            text_locator.scroll_into_view_if_needed(timeout=3000)
            # 找到文本附近的 input
            input_locator = text_locator.locator("xpath=following::input[1] | preceding::input[1]").first
            input_locator.fill(value, timeout=5000)
            return
        except Exception:
            pass

    page.fill(selector, value, timeout=8000)


def _robust_select(page, selector: str, value: str, desc: str = "") -> None:
    """健壮下拉选择：普通选择 → 滚动后选择 → 强制选择."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    # 第一次尝试
    try:
        page.select_option(selector, value, timeout=8000)
        return
    except PlaywrightTimeout:
        pass
    except Exception:
        pass

    # 第二次尝试：滚动后选择
    try:
        locator = page.locator(selector).first
        locator.scroll_into_view_if_needed(timeout=3000)
        locator.select_option(value, timeout=5000)
        return
    except Exception:
        pass

    # 第三次尝试：点击展开后按文本选择
    try:
        page.click(selector, force=True, timeout=5000)
        page.wait_for_timeout(500)
        # 尝试按选项文本点击
        option_locator = page.locator(f"option[value='{value}'], li:has-text('{value}')").first
        option_locator.click(timeout=5000)
        return
    except Exception:
        pass

    page.select_option(selector, value, timeout=8000)


def _robust_press(page, selector: str, key: str, desc: str = "") -> None:
    """健壮按键：普通按键 → 滚动后按键 → 强制聚焦后按键."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    # 第一次尝试
    try:
        page.press(selector, key, timeout=8000)
        return
    except PlaywrightTimeout:
        pass
    except Exception:
        pass

    # 第二次尝试：滚动后按键
    try:
        locator = page.locator(selector).first
        locator.scroll_into_view_if_needed(timeout=3000)
        locator.press(key, timeout=5000)
        return
    except Exception:
        pass

    # 第三次尝试：强制聚焦后按键
    try:
        page.focus(selector, timeout=5000)
        page.keyboard.press(key)
        return
    except Exception:
        pass

    page.press(selector, key, timeout=8000)


def _robust_hover(page, selector: str, desc: str = "") -> None:
    """健壮悬停：普通悬停 → 滚动后悬停 → JS dispatch mousemove."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    # 第一次尝试：普通 hover
    try:
        page.hover(selector, timeout=8000)
        return
    except PlaywrightTimeout:
        pass
    except Exception:
        pass

    # 第二次尝试：滚动后 hover
    try:
        locator = page.locator(selector).first
        locator.scroll_into_view_if_needed(timeout=3000)
        locator.hover(timeout=5000)
        return
    except Exception:
        pass

    # 第三次尝试：强制 hover（忽略可见性）
    try:
        page.hover(selector, force=True, timeout=5000)
        return
    except Exception:
        pass

    # 第四次尝试：JS dispatchEvent mouseover/mousemove
    try:
        page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (el) {
                    el.scrollIntoView();
                    ['mouseover', 'mousemove', 'mouseenter'].forEach((type) => {
                        el.dispatchEvent(new MouseEvent(type, {bubbles: true}));
                    });
                    return true;
                }
                return false;
            }""",
            selector,
        )
        return
    except Exception:
        pass

    page.hover(selector, timeout=8000)


def _robust_scroll(page, selector: str, direction: str, amount: int, desc: str = "") -> None:
    """健壮滚动：在元素内或页面上滚动指定方向和距离.

    direction: up/down
    amount: 像素数
    """
    amount = int(amount) if amount else 500
    delta = -amount if direction == "up" else amount

    # 第一次尝试：使用 page.mouse.wheel 在页面级滚动（先定位元素中心）
    try:
        if selector:
            locator = page.locator(selector).first
            try:
                box = locator.bounding_box(timeout=3000)
            except Exception:
                box = None
            if box:
                # 将鼠标移到元素中心再滚动
                page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.wheel(0, delta)
        return
    except Exception:
        pass

    # 第二次尝试：JS scrollTop/scrollLeft
    try:
        page.evaluate(
            """(args) => {
                const [sel, dir, amt] = args;
                const el = sel ? document.querySelector(sel) : document.documentElement;
                if (!el) return false;
                if (dir === 'up') {
                    el.scrollTop -= amt;
                } else {
                    el.scrollTop += amt;
                }
                return true;
            }""",
            [selector, direction, amount],
        )
        return
    except Exception:
        pass

    # 兜底：window.scrollBy
    try:
        page.evaluate(
            """(args) => {
                const [dir, amt] = args;
                window.scrollBy(0, dir === 'up' ? -amt : amt);
                return true;
            }""",
            [direction, amount],
        )
    except Exception:
        pass


def _robust_drag(page, source: str, target: str, desc: str = "") -> None:
    """健壮拖拽：使用 drag_to → 手动 mouse down/move/up 兜底."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    # 第一次尝试：使用 drag_to
    try:
        source_loc = page.locator(source).first
        target_loc = page.locator(target).first
        source_loc.drag_to(target_loc, timeout=8000)
        return
    except PlaywrightTimeout:
        pass
    except Exception:
        pass

    # 第二次尝试：手动 mouse.down → mouse.move → mouse.up
    try:
        source_loc = page.locator(source).first
        target_loc = page.locator(target).first
        source_box = source_loc.bounding_box(timeout=3000)
        target_box = target_loc.bounding_box(timeout=3000)
        if source_box and target_box:
            page.mouse.move(source_box["x"] + source_box["width"] / 2,
                            source_box["y"] + source_box["height"] / 2)
            page.mouse.down()
            # 分步移动更接近真实拖拽
            steps = 5
            for i in range(1, steps + 1):
                page.mouse.move(
                    source_box["x"] + (target_box["x"] - source_box["x"]) * i / steps
                    + target_box["width"] / 2 * (i / steps),
                    source_box["y"] + (target_box["y"] - source_box["y"]) * i / steps
                    + target_box["height"] / 2 * (i / steps),
                    steps=2,
                )
            page.mouse.move(target_box["x"] + target_box["width"] / 2,
                            target_box["y"] + target_box["height"] / 2)
            page.mouse.up()
            return
    except Exception:
        pass

    # 第三次尝试：HTML5 drag and drop via JS（dispatch dragstart/drop 事件）
    try:
        page.evaluate(
            """(args) => {
                const [srcSel, tgtSel] = args;
                const src = document.querySelector(srcSel);
                const tgt = document.querySelector(tgtSel);
                if (!src || !tgt) return false;
                const dataTransfer = new DataTransfer();
                src.dispatchEvent(new DragEvent('dragstart', {bubbles: true, dataTransfer}));
                tgt.dispatchEvent(new DragEvent('drop', {bubbles: true, dataTransfer}));
                src.dispatchEvent(new DragEvent('dragend', {bubbles: true, dataTransfer}));
                return true;
            }""",
            [source, target],
        )
    except Exception:
        pass


def _robust_upload(page, selector: str, file_path: str, desc: str = "") -> None:
    """健壮文件上传：使用 set_input_files → 点击触发后设置."""
    import os

    if not file_path:
        raise ValueError("upload 操作需要 file_path")

    # file_path 可能是绝对路径或相对路径，统一处理
    if not os.path.isabs(file_path):
        # 相对路径基于当前工作目录
        file_path = os.path.abspath(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"上传文件不存在: {file_path}")

    # 第一次尝试：直接 set_input_files
    try:
        page.set_input_files(selector, file_path, timeout=8000)
        return
    except Exception:
        pass

    # 第二次尝试：定位 input[type=file] 后设置（可能有多个隐藏的）
    try:
        locator = page.locator(selector).first
        locator.scroll_into_view_if_needed(timeout=3000)
        locator.set_input_files(file_path, timeout=5000)
        return
    except Exception:
        pass

    # 第三次尝试：通过 JS 显示所有 input[type=file] 后再设置
    try:
        page.evaluate(
            """() => {
                document.querySelectorAll('input[type=file]').forEach((el) => {
                    el.style.display = 'block';
                    el.style.visibility = 'visible';
                    el.style.opacity = '1';
                });
                return true;
            }"""
        )
        page.set_input_files(selector, file_path, timeout=5000)
    except Exception:
        # 最后再抛出原始异常
        page.set_input_files(selector, file_path, timeout=8000)


def _robust_download(page, selector: str, save_path: str, desc: str = "") -> str:
    """健壮下载：监听 download 事件 → 点击触发 → 保存到指定路径.

    返回实际保存路径。
    """
    import os

    if not save_path:
        raise ValueError("download 操作需要 save_path")

    save_dir = os.path.dirname(os.path.abspath(save_path))
    os.makedirs(save_dir, exist_ok=True)

    # 第一次尝试：使用 expect_download
    try:
        with page.expect_download(timeout=15000) as download_info:
            try:
                page.click(selector, timeout=8000)
            except Exception:
                # 强制点击
                page.click(selector, force=True, timeout=5000)
        download = download_info.value
        download.save_as(save_path)
        return save_path
    except Exception:
        pass

    # 第二次尝试：注册 download 事件回调后点击
    try:
        downloaded_path = {"path": None}

        def _on_download(download):
            try:
                download.save_as(save_path)
                downloaded_path["path"] = save_path
            except Exception:
                pass

        page.on("download", _on_download)
        try:
            page.click(selector, timeout=8000)
        except Exception:
            page.click(selector, force=True, timeout=5000)
        # 等待下载完成
        page.wait_for_timeout(3000)
        if downloaded_path["path"]:
            return downloaded_path["path"]
        page.remove_listener("download", _on_download)
    except Exception:
        pass

    # 兜底：直接获取链接 href 并用 JS fetch 下载（仅适用于直接链接）
    try:
        href = page.get_attribute(selector, "href", timeout=3000)
        if href:
            import urllib.request
            base = page.url
            from urllib.parse import urljoin
            full_url = urljoin(base, href)
            urllib.request.urlretrieve(full_url, save_path)
            return save_path
    except Exception:
        pass

    raise RuntimeError(f"下载失败: 无法从 {selector} 获取文件")


# ---------------------------------------------------------------------------
# Playwright UI 测试执行引擎
# ---------------------------------------------------------------------------

def _expand_step_groups(steps: list[dict], db: Session | None) -> list[dict]:
    """递归展开步骤组引用，返回扁平化的步骤列表.

    遇到 action="step_group" 时：
    1. 从数据库查询 step_library_id 对应的步骤组
    2. 递归展开其子步骤（支持嵌套）
    3. 递增 step_library 的 usage_count
    """
    if not db:
        return list(steps)
    from app.models.step_library import StepLibrary

    flat: list[dict] = []
    for step in steps:
        if step.get("action") == "step_group":
            sg_id = step.get("step_library_id")
            if not sg_id:
                # 缺少 step_library_id，跳过该步骤
                continue
            sg = db.get(StepLibrary, sg_id)
            if not sg:
                raise ValueError(f"步骤组不存在: {sg_id}")
            # 递增引用计数
            try:
                sg.usage_count = (sg.usage_count or 0) + 1
                db.commit()
            except Exception:
                db.rollback()
            # 递归展开子步骤
            sub_steps = _expand_step_groups(sg.steps or [], db)
            flat.extend(sub_steps)
        else:
            flat.append(dict(step))
    return flat


def _execute_steps_with_playwright(
    url: str,
    browser_type: str,
    steps: list[dict],
    db: Session | None = None,
    *,
    job_id: str | None = None,
    artifact_dir: str | None = None,
) -> dict:
    """使用 Playwright 执行 UI 测试步骤，返回执行结果.

    支持的步骤动作：
    - navigate: 导航到指定 URL（value 为 URL，或默认用例起始 URL）
    - click: 点击元素（selector 为 CSS/XPath 选择器）
    - input: 在输入框中输入文本（selector + value）
    - assert: 断言元素文本包含指定值（selector + value）
    - wait: 等待指定秒数（value 为数字字符串）
    - screenshot: 截图
    - select: 选择下拉选项（selector + value）
    - press: 按键（selector + value 为键名如 Enter/Tab）
    - hover: 悬停元素（selector）
    - drag: 拖拽元素（source + target）
    - scroll: 滚动页面或元素（selector 可选 + direction[up/down] + amount）
    - upload: 上传文件（selector + file_path/artifact_id，file_path 不存在时回退用 value）
    - download: 下载文件（selector + save_path/artifact_id，save_path 不存在时回退用 value）
    - step_group: 引用可复用步骤组，执行前会被展开为子步骤

    Phase 4 UI 增强：
    - 启用 Playwright Trace，执行结束保存到 ``{artifact_dir}/trace_{job_id}.zip``
    - 聚合 console.error / pageerror，返回在 ``errors`` 字段
    - 步骤失败时捕获当前 DOM 快照，附加到 ``step_info["dom_snapshot"]``
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

    # 展开所有 step_group 引用，得到扁平化步骤列表
    flat_steps = _expand_step_groups(steps, db)

    step_results: list[dict] = []
    passed = 0
    failed = 0
    error_msg = None
    screenshots: list[str] = []  # base64 截图列表
    # Phase 4: console.error / pageerror / 网络错误聚合
    errors: list[dict] = []
    trace_path: str | None = None

    browser_map = {
        "chrome": "chromium",
        "firefox": "firefox",
        "edge": "chromium",  # Edge 基于 Chromium
    }
    pw_browser = browser_map.get(browser_type, "chromium")
    # edge 使用 channel 参数
    channel = "msedge" if browser_type == "edge" else None

    try:
        with sync_playwright() as p:
            browser_launcher = getattr(p, pw_browser, p.chromium)
            launch_kwargs = {"headless": True}
            if channel:
                launch_kwargs["channel"] = channel
            try:
                browser = browser_launcher.launch(**launch_kwargs)
            except Exception:
                # 如果指定 channel 失败（如 Edge 未安装），回退到普通 Chromium
                browser = browser_launcher.launch(headless=True)

            # Phase 4: 通过 context 创建 page，以便启用 tracing
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                locale="zh-CN",
            )
            # 启用 Trace 收集
            try:
                context.tracing.start(
                    screenshots=True, snapshots=True, sources=True
                )
            except Exception:
                # 极少数情况下 tracing 不可用，不应阻断主流程
                pass

            page = context.new_page()
            # 设置默认超时
            page.set_default_timeout(15000)

            # Phase 4: 注册 console / pageerror 事件聚合
            def _on_console(msg):
                try:
                    if msg.type == "error":
                        errors.append({"type": "console", "text": msg.text})
                except Exception:
                    pass

            def _on_pageerror(err):
                try:
                    errors.append({"type": "pageerror", "text": str(err)})
                except Exception:
                    pass

            def _on_request_failed(request):
                try:
                    errors.append({
                        "type": "network",
                        "text": f"{request.method} {request.url} failed",
                        "url": request.url,
                    })
                except Exception:
                    pass

            try:
                page.on("console", _on_console)
                page.on("pageerror", _on_pageerror)
                page.on("requestfailed", _on_request_failed)
            except Exception:
                pass

            # 第一步：导航到起始 URL
            current_url = url
            for idx, step in enumerate(flat_steps):
                action = step.get("action", "")
                selector = step.get("selector")
                value = step.get("value")
                desc = step.get("description", "")
                # 扩展字段：用于 hover/drag/scroll/upload/download 等新动作
                source_sel = step.get("source")
                target_sel = step.get("target")
                direction = step.get("direction", "down")
                amount = step.get("amount", 500)
                artifact_id = step.get("artifact_id")
                file_path = step.get("file_path") or step.get("value")
                save_path = step.get("save_path") or step.get("value")
                step_start = time.time()
                step_info = {
                    "step": idx + 1,
                    "action": action,
                    "selector": selector,
                    "value": value,
                    "description": desc,
                    "status": "passed",
                    "duration": 0,
                    "error": None,
                }

                try:
                    if action == "navigate":
                        target_url = value or url
                        page.goto(target_url, wait_until="domcontentloaded")
                        current_url = target_url
                        step_info["message"] = f"导航到 {target_url}"

                    elif action == "click":
                        if not selector:
                            raise ValueError("click 操作需要 selector")
                        _robust_click(page, selector, desc)
                        step_info["message"] = f"点击 {selector}"

                    elif action == "input":
                        if not selector:
                            raise ValueError("input 操作需要 selector")
                        _robust_input(page, selector, value or "", desc)
                        step_info["message"] = f"输入 '{value}' 到 {selector}"

                    elif action == "assert":
                        if not selector:
                            raise ValueError("assert 操作需要 selector")
                        # 等待元素出现
                        page.wait_for_selector(selector, timeout=10000)
                        actual_text = page.inner_text(selector)
                        if value and value not in actual_text:
                            raise AssertionError(
                                f"断言失败: 期望包含 '{value}'，实际为 '{actual_text}'"
                            )
                        step_info["message"] = f"断言 {selector} 包含 '{value}'"

                    elif action == "wait":
                        wait_sec = float(value) if value else 1
                        time.sleep(wait_sec)
                        step_info["message"] = f"等待 {wait_sec}s"

                    elif action == "screenshot":
                        screenshot_bytes = page.screenshot()
                        import base64
                        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                        screenshots.append(screenshot_b64)
                        step_info["message"] = "截图成功"
                        step_info["screenshot"] = True

                    elif action == "select":
                        if not selector:
                            raise ValueError("select 操作需要 selector")
                        _robust_select(page, selector, value or "", desc)
                        step_info["message"] = f"选择 {selector} = '{value}'"

                    elif action == "press":
                        if not selector:
                            raise ValueError("press 操作需要 selector")
                        _robust_press(page, selector, value or "Enter", desc)
                        step_info["message"] = f"按键 {value} on {selector}"

                    elif action == "hover":
                        if not selector:
                            raise ValueError("hover 操作需要 selector")
                        _robust_hover(page, selector, desc)
                        step_info["message"] = f"悬停 {selector}"

                    elif action == "drag":
                        if not source_sel or not target_sel:
                            raise ValueError("drag 操作需要 source 和 target")
                        _robust_drag(page, source_sel, target_sel, desc)
                        step_info["message"] = f"拖拽 {source_sel} → {target_sel}"

                    elif action == "scroll":
                        # selector 可选，不传则滚动整个页面
                        _robust_scroll(page, selector or "", direction, amount, desc)
                        step_info["message"] = f"滚动 {direction} {amount}px"

                    elif action == "upload":
                        if not selector:
                            raise ValueError("upload 操作需要 selector")
                        # SEC-06: 优先 artifact_id，回退 file_path（需校验）
                        resolved_path = resolve_artifact_path(artifact_id, file_path)
                        _robust_upload(page, selector, resolved_path, desc)
                        step_info["message"] = f"上传文件 {resolved_path}"

                    elif action == "download":
                        if not selector:
                            raise ValueError("download 操作需要 selector")
                        # SEC-06: 校验保存路径安全性（artifact_id 为未来保存到对象存储预留）
                        resolved_path = resolve_artifact_path(
                            artifact_id,
                            save_path,
                            for_write=True,
                        )
                        actual_path = _robust_download(page, selector, resolved_path, desc)
                        step_info["message"] = f"下载文件到 {actual_path}"
                        step_info["save_path"] = actual_path

                    else:
                        raise ValueError(f"不支持的动作类型: {action}")

                    step_info["duration"] = round(time.time() - step_start, 3)
                    passed += 1

                except Exception as e:
                    step_info["status"] = "failed"
                    step_info["duration"] = round(time.time() - step_start, 3)
                    step_info["error"] = str(e)
                    failed += 1
                    # 截图记录失败现场
                    try:
                        screenshot_bytes = page.screenshot()
                        import base64
                        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                        screenshots.append(screenshot_b64)
                        step_info["screenshot"] = True
                        step_info["screenshot_error"] = True
                    except Exception:
                        pass
                    # Phase 4: 失败步骤 DOM 快照
                    try:
                        dom_snapshot = page.content()
                        step_info["dom_snapshot"] = dom_snapshot
                    except Exception:
                        pass
                    # 失败后停止后续步骤
                    error_msg = f"步骤 {idx + 1} ({action}) 失败: {e}"
                    step_results.append(step_info)
                    break

                step_results.append(step_info)

            # 最终截图
            try:
                final_screenshot = page.screenshot()
                import base64
                final_b64 = base64.b64encode(final_screenshot).decode("utf-8")
                screenshots.append(final_b64)
            except Exception:
                pass

            # Phase 4: 停止 Trace 并保存到 artifact_dir
            try:
                if artifact_dir and job_id:
                    import os
                    os.makedirs(artifact_dir, exist_ok=True)
                    trace_path = os.path.join(artifact_dir, f"trace_{job_id}.zip")
                    context.tracing.stop(path=trace_path)
                else:
                    # 未指定保存路径时仅停止收集，不落盘
                    context.tracing.stop()
            except Exception:
                pass

            browser.close()

    except Exception as e:
        error_msg = f"浏览器启动/执行异常: {e}"
        if not step_results:
            step_results.append({
                "step": 0,
                "action": "init",
                "status": "error",
                "duration": 0,
                "error": str(e),
            })
        failed += 1

    total = len(flat_steps)
    status = "passed" if failed == 0 and passed > 0 else ("failed" if failed > 0 else "error")

    return {
        "status": status,
        "total_steps": total,
        "passed_steps": passed,
        "failed_steps": failed,
        "error": error_msg,
        "steps": step_results,
        "screenshots": screenshots,
        "final_url": current_url if "current_url" in locals() else url,
        # Phase 4 新增字段
        "errors": errors,
        "trace_path": trace_path,
    }


def _execute_with_retry(
    url: str,
    browser_type: str,
    steps: list[dict],
    retry_count: int = 0,
    retry_interval: float = 2.0,
    db: Session | None = None,
    *,
    job_id: str | None = None,
    artifact_dir: str | None = None,
) -> tuple[dict, list[dict], int]:
    """执行 UI 测试步骤，失败时按 retry_count 自动重试.

    在 _execute_steps_with_playwright 外层包裹重试逻辑：
    - 首次执行 + 最多 retry_count 次重试
    - 任意一次成功即停止，最终状态取首次成功的结果
    - 每次尝试之间等待 retry_interval 秒

    Phase 4: 透传 job_id / artifact_dir 以启用 Playwright Trace 保存。

    返回: (最终结果, 每次尝试摘要列表, 最终成功尝试序号)
    """
    total_attempts = max(retry_count + 1, 1)
    retry_attempts: list[dict] = []
    final_result: dict | None = None
    final_attempt_num = total_attempts

    for attempt in range(total_attempts):
        attempt_start = time.time()
        result = _execute_steps_with_playwright(
            url=url,
            browser_type=browser_type,
            steps=steps,
            db=db,
            job_id=job_id,
            artifact_dir=artifact_dir,
        )
        attempt_duration = round(time.time() - attempt_start, 3)
        retry_attempts.append({
            "attempt": attempt + 1,
            "status": result["status"],
            "duration": attempt_duration,
            "error": result["error"],
        })
        final_result = result
        final_attempt_num = attempt + 1
        # 通过则不再重试
        if result["status"] == "passed":
            break
        # 未通过且还有重试机会，则等待后重试
        if attempt < total_attempts - 1 and retry_interval > 0:
            time.sleep(retry_interval)

    return final_result, retry_attempts, final_attempt_num


def execute_ui_case(
    *,
    url: str,
    browser_type: str,
    steps: list[dict],
    retry_count: int = 0,
    retry_interval: float = 2.0,
    db: Session | None = None,
    job_id: str | None = None,
    artifact_dir: str | None = None,
) -> tuple[dict, list[dict], int]:
    """执行 UI 测试用例的公共入口.

    Phase 4: 可选传入 job_id / artifact_dir 以启用 Playwright Trace 保存。

    返回: (最终结果, 每次尝试摘要列表, 最终成功尝试序号)
    """
    return _execute_with_retry(
        url=url,
        browser_type=browser_type,
        steps=steps,
        retry_count=retry_count,
        retry_interval=retry_interval,
        db=db,
        job_id=job_id,
        artifact_dir=artifact_dir,
    )
