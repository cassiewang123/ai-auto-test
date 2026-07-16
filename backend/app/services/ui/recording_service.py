"""UI 测试录屏服务.

REF-02: 从 ``app/api/v1/ui_test_cases.py`` 提取的录制逻辑，包括：
- 录屏注入脚本 ``RECORDING_SCRIPT``
- 全局录制会话存储 ``_recording_sessions``
- 后台录制线程 ``_recording_worker``
- 公共接口：``start_recording`` / ``get_recording_events`` / ``stop_recording`` / ``save_recording_as_case``
"""
from __future__ import annotations

import json
import threading
import time
import traceback
import uuid as _uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.ui_test_case import UiTestCase


# 全局录制会话存储（线程安全，GIL 保护）
_recording_sessions: dict[str, dict] = {}


# 注入到目标页面的录屏脚本
# 通过 page.add_init_script 在每次页面加载/导航时自动注入
# 使用 console.log 上报事件，Python 端通过 page.on("console") 捕获
RECORDING_SCRIPT = """
(function() {
    // 防止重复注入
    if (window.__UI_TEST_INJECTED) return;
    window.__UI_TEST_INJECTED = true;
    window.__UI_TEST_RECORDING = true;
    // 事件缓冲区：Python 端通过 page.evaluate() 定期采集并清空
    window.__UI_TEST_EVENTS = window.__UI_TEST_EVENTS || [];

    function getSelector(element) {
        if (!element || element === document.body) return 'body';
        if (element.id) return '#' + CSS.escape(element.id);
        if (element.name) {
            var named = document.querySelectorAll('[name="' + element.name + '"]');
            if (named.length === 1) return '[name="' + element.name + '"]';
        }
        if (element.getAttribute('data-testid')) {
            return '[data-testid="' + element.getAttribute('data-testid') + '"]';
        }
        if (element.className && typeof element.className === 'string') {
            var classes = element.className.trim().split(/\\s+/).filter(Boolean);
            if (classes.length > 0) {
                var selector = classes.map(function(c) { return '.' + CSS.escape(c); }).join('');
                try {
                    if (document.querySelectorAll(selector).length === 1) return selector;
                } catch(e) {}
            }
        }
        var path = [];
        var current = element;
        while (current && current !== document.documentElement) {
            var parent = current.parentElement;
            if (!parent) break;
            var index = 1;
            var sibling = current.previousElementSibling;
            while (sibling) {
                if (sibling.tagName === current.tagName) index++;
                sibling = sibling.previousElementSibling;
            }
            var part = current.tagName.toLowerCase();
            var sameTagCount = 0;
            for (var i = 0; i < parent.children.length; i++) {
                if (parent.children[i].tagName === current.tagName) sameTagCount++;
            }
            if (sameTagCount > 1) part += ':nth-of-type(' + index + ')';
            path.unshift(part);
            current = parent;
        }
        return path.join(' > ');
    }

    function getDesc(element, action) {
        var text = '';
        if (element.textContent) text = element.textContent.trim().substring(0, 40);
        if (!text) text = element.getAttribute('placeholder') || '';
        if (!text) text = element.getAttribute('aria-label') || '';
        if (!text) text = element.tagName.toLowerCase();
        var actionMap = {click: '点击', input: '输入', select: '选择', navigate: '导航', press: '按键'};
        var actionText = actionMap[action] || action;
        return actionText + ' ' + text;
    }

    function reportEvent(event) {
        try {
            window.__UI_TEST_EVENTS.push(event);
            console.log('__RECORD_EVENT__:' + JSON.stringify(event));
        } catch(e) {}
    }

    // 录制点击（防抖：500ms 内同一选择器只记录一次）
    var lastClick = { selector: '', time: 0 };
    document.addEventListener('click', function(e) {
        if (!window.__UI_TEST_RECORDING) return;
        var target = e.target;
        if (target.tagName === 'SCRIPT') return;
        var sel = getSelector(target);
        var now = Date.now();
        if (lastClick.selector === sel && now - lastClick.time < 500) return;
        lastClick = { selector: sel, time: now };
        reportEvent({
            action: 'click',
            selector: sel,
            value: '',
            timestamp: now,
            description: getDesc(target, 'click')
        });
    }, true);

    // 录制输入（防抖 500ms）
    var inputTimer = null;
    var inputTarget = null;
    var inputValue = null;
    document.addEventListener('input', function(e) {
        if (!window.__UI_TEST_RECORDING) return;
        var target = e.target;
        if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
            inputTarget = target;
            inputValue = target.value;
            if (inputTimer) clearTimeout(inputTimer);
            inputTimer = setTimeout(function() {
                reportEvent({
                    action: 'input',
                    selector: getSelector(inputTarget),
                    value: inputValue,
                    timestamp: Date.now(),
                    description: getDesc(inputTarget, 'input') + ' "' + inputValue + '"'
                });
                inputTimer = null;
            }, 500);
        }
    }, true);

    // 录制下拉选择
    document.addEventListener('change', function(e) {
        if (!window.__UI_TEST_RECORDING) return;
        var target = e.target;
        if (target.tagName === 'SELECT') {
            reportEvent({
                action: 'select',
                selector: getSelector(target),
                value: target.value,
                timestamp: Date.now(),
                description: getDesc(target, 'select') + ' "' + target.value + '"'
            });
        }
    }, true);

    // 录制按键（仅 Enter/Tab/Escape）
    document.addEventListener('keydown', function(e) {
        if (!window.__UI_TEST_RECORDING) return;
        var specialKeys = ['Enter', 'Tab', 'Escape'];
        if (specialKeys.indexOf(e.key) !== -1) {
            reportEvent({
                action: 'press',
                selector: getSelector(e.target),
                value: e.key,
                timestamp: Date.now(),
                description: '按键 ' + e.key
            });
        }
    }, true);
})();
"""


def _recording_worker(session_id: str, url: str, browser_type: str) -> None:
    """后台线程：运行 Playwright 浏览器，注入录屏脚本，循环采集事件."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Recording worker started: session={session_id}, url={url}, browser={browser_type}")

    from playwright.sync_api import sync_playwright

    session = _recording_sessions[session_id]
    browser = None

    try:
        with sync_playwright() as p:
            browser_map = {
                "chrome": "chromium",
                "firefox": "firefox",
                "edge": "chromium",
            }
            pw_browser = browser_map.get(browser_type, "chromium")
            channel = "msedge" if browser_type == "edge" else None
            browser_launcher = getattr(p, pw_browser, p.chromium)

            launch_kwargs = {"headless": False}  # 有头模式，用户可交互
            if channel:
                launch_kwargs["channel"] = channel
            try:
                browser = browser_launcher.launch(**launch_kwargs)
            except Exception:
                browser = browser_launcher.launch(headless=False)

            page = browser.new_page(
                viewport={"width": 1280, "height": 720},
                locale="zh-CN",
            )
            page.set_default_timeout(30000)

            session["page_url"] = url

            # 用 console.log 上报事件：JS 端 console.log 特定前缀的消息，Python 端通过 page.on("console") 捕获
            # 这是最可靠的方式，不依赖 expose_function 的时序
            def _on_console(msg):
                text = msg.text
                if "__RECORD_EVENT__:" in text:
                    try:
                        idx = text.index("__RECORD_EVENT__:")
                        event_json = text[idx + len("__RECORD_EVENT__:"):]
                        ev = json.loads(event_json)
                        session["events"].append(ev)
                        logger.info(f"Recorded event: {ev.get('action')} selector={ev.get('selector', '')[:50]}")
                    except Exception as e:
                        logger.warning(f"Failed to parse record event: {e}, text={text[:100]}")

            page.on("console", _on_console)

            # 使用 add_init_script：每次页面加载/导航时自动注入录屏脚本
            page.add_init_script(RECORDING_SCRIPT)

            # 导航到目标 URL（add_init_script 会在页面加载时自动注入录屏脚本）
            page.goto(url, wait_until="domcontentloaded")

            # 等待 SPA 路由稳定
            time.sleep(3)

            # 记录初始导航事件（始终使用用户输入的原始 URL）
            logger.info(f"Recording initial navigate event with URL: {url}")
            session["events"].append({
                "action": "navigate",
                "selector": "",
                "value": url,
                "timestamp": int(time.time() * 1000),
                "description": f"导航到 {url}",
            })
            session["last_page_url"] = page.url

            session["is_active"] = True
            session["status"] = "recording"

            # 轮询循环：采集事件 + 更新 page_url 状态
            # 关键：必须用 page.wait_for_timeout() 而非 time.sleep()，
            # 否则 Playwright 事件循环不会被泵送，page.on("console") 回调永远不触发
            while not session.get("stop_flag", False):
                try:
                    session["page_url"] = page.url
                    # 主采集机制：通过 page.evaluate 直接读取页面 JS 全局数组
                    # 这比 console.log + page.on("console") 更可靠
                    try:
                        new_events = page.evaluate(
                            "() => { const e = window.__UI_TEST_EVENTS || []; "
                            "window.__UI_TEST_EVENTS = []; return e; }"
                        )
                        if new_events:
                            for ev in new_events:
                                session["events"].append(ev)
                                logger.info(
                                    f"Recorded event via evaluate: "
                                    f"{ev.get('action')} selector={ev.get('selector', '')[:50]}"
                                )
                    except Exception as eval_err:
                        logger.debug(f"evaluate collection skipped: {eval_err}")
                    # 泵送 Playwright 事件循环（让 console handler 作为备份也能工作）
                    page.wait_for_timeout(1000)
                except Exception as loop_err:
                    logger.warning(f"Polling loop error: {loop_err}")
                    time.sleep(1)

            # 停止录制
            session["status"] = "stopped"
            session["is_active"] = False

            try:
                browser.close()
            except Exception:
                pass

    except Exception as exc:
        session["status"] = "error"
        session["error"] = str(exc)
        session["is_active"] = False
        traceback.print_exc()
        if browser:
            try:
                browser.close()
            except Exception:
                pass


def _events_to_steps(raw_events: list[dict]) -> list[dict]:
    """将原始录制事件转换为 UI 测试步骤."""
    steps = []
    for ev in raw_events:
        steps.append({
            "action": ev.get("action", ""),
            "selector": ev.get("selector", ""),
            "value": ev.get("value", ""),
            "description": ev.get("description", ""),
        })
    return steps


def start_recording(url: str, browser_type: str) -> dict:
    """启动浏览器录屏会话，返回会话初始信息."""
    session_id = str(_uuid.uuid4())

    _recording_sessions[session_id] = {
        "session_id": session_id,
        "url": url,
        "browser_type": browser_type,
        "events": [],
        "is_active": False,
        "stop_flag": False,
        "status": "starting",
        "page_url": url,
        "started_at": datetime.now().isoformat(),
        "error": None,
    }

    # 启动后台录制线程
    thread = threading.Thread(
        target=_recording_worker,
        args=(session_id, url, browser_type),
        daemon=True,
    )
    thread.start()
    _recording_sessions[session_id]["thread"] = thread

    return {
        "session_id": session_id,
        "url": url,
        "browser_type": browser_type,
        "status": "starting",
        "message": "浏览器正在启动，请稍候...",
    }


def get_recording_events(session_id: str) -> dict:
    """获取录屏会话的实时事件（前端轮询调用）."""
    session = _recording_sessions.get(session_id)
    if not session:
        raise NotFoundError("录屏会话", session_id)

    return {
        "session_id": session_id,
        "status": session.get("status", "unknown"),
        "is_active": session.get("is_active", False),
        "events": session.get("events", []),
        "event_count": len(session.get("events", [])),
        "page_url": session.get("page_url", ""),
        "error": session.get("error"),
    }


def stop_recording(session_id: str) -> dict:
    """停止录屏，将捕获的事件转换为 UI 测试步骤并返回."""
    session = _recording_sessions.get(session_id)
    if not session:
        raise NotFoundError("录屏会话", session_id)

    # 设置停止标志
    session["stop_flag"] = True

    # 等待录制线程结束（最多 10 秒）
    thread = session.get("thread")
    if thread and thread.is_alive():
        thread.join(timeout=10)

    # 获取最终事件列表
    raw_events = session.get("events", [])
    steps = _events_to_steps(raw_events)

    # 清理会话
    _recording_sessions.pop(session_id, None)

    return {
        "session_id": session_id,
        "status": "completed",
        "total_events": len(raw_events),
        "steps": steps,
        "message": f"录制完成，共捕获 {len(steps)} 个步骤",
    }


def save_recording_as_case(
    session_id: str,
    *,
    title: str,
    project_id: str | None = None,
    url: str | None = None,
    browser_type: str = "chrome",
    db: Session,
) -> dict:
    """停止录制并保存为 UI 测试用例，返回用例信息."""
    session = _recording_sessions.get(session_id)
    if not session:
        raise NotFoundError("录屏会话", session_id)

    # 设置停止标志
    session["stop_flag"] = True
    thread = session.get("thread")
    if thread and thread.is_alive():
        thread.join(timeout=10)

    raw_events = session.get("events", [])
    steps = _events_to_steps(raw_events)

    # 创建 UI 测试用例
    case_url = url or session.get("url", "")
    case = UiTestCase(
        title=title,
        url=case_url,
        browser_type=browser_type,
        steps=steps,
        project_id=project_id,
        is_active=True,
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    # 清理会话
    _recording_sessions.pop(session_id, None)

    return {
        "case_id": case.id,
        "title": case.title,
        "url": case.url,
        "steps": steps,
        "total_steps": len(steps),
        "message": f"已保存为 UI 测试用例，共 {len(steps)} 个步骤",
    }
