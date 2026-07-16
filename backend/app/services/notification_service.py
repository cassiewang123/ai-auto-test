"""Webhook 通知服务：飞书/钉钉/企微/Slack 消息发送.

签名算法（飞书/钉钉一致）：
    sign = base64(HmacSHA256(key=secret, msg=timestamp + "\\n" + secret))
飞书：timestamp 单位为秒，sign 放入请求体。
钉钉：timestamp 单位为毫秒，sign 与 timestamp 拼接为 URL query 参数。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.services.security.secret_crypto import (
    decrypt_secret,
    decrypt_url,
    redact_url_from_text,
)

logger = logging.getLogger(__name__)

# 各事件类型对应的标题
_EVENT_TITLES = {
    "test_run.completed": "测试执行完成",
    "test_run.failed": "测试执行失败",
    "scheduled_task.completed": "定时任务执行完成",
    "perf_test.completed": "性能测试完成",
}


# ---------------------------------------------------------------------------
# 加签
# ---------------------------------------------------------------------------
def gen_sign(secret: str, timestamp: str) -> str:
    """生成加签：base64(HmacSHA256(key=secret, msg=timestamp + "\\n" + secret)).

    飞书与钉钉共用此算法，区别在 timestamp 单位与 sign 传递方式。
    """
    plaintext_secret = decrypt_secret(secret)
    if plaintext_secret is None:
        plaintext_secret = ""
    string_to_sign = f"{timestamp}\n{plaintext_secret}"
    hmac_code = hmac.new(
        plaintext_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def gen_feishu_sign(secret: str, timestamp: str) -> str:
    """飞书加签（timestamp 单位：秒）."""
    return gen_sign(secret, timestamp)


def gen_dingtalk_sign(secret: str, timestamp: str) -> str:
    """钉钉加签（timestamp 单位：毫秒）."""
    return gen_sign(secret, timestamp)


# ---------------------------------------------------------------------------
# 消息格式化
# ---------------------------------------------------------------------------
def format_message(event_type: str, context: dict[str, Any]) -> str:
    """根据事件类型与上下文格式化通知内容."""
    ctx = context or {}
    if event_type == "test_run.completed":
        return (
            f"测试执行完成 | 总数:{ctx.get('total', 0)} "
            f"通过:{ctx.get('passed', 0)} 失败:{ctx.get('failed', 0)} "
            f"耗时:{ctx.get('duration', 0)}s"
        )
    if event_type == "test_run.failed":
        return (
            f"测试执行失败 | 失败:{ctx.get('failed', 0)} "
            f"错误:{ctx.get('error', 0)}"
        )
    if event_type == "scheduled_task.completed":
        return (
            f"定时任务[{ctx.get('task_name', '')}]执行完成 | "
            f"通过率:{ctx.get('pass_rate', 0)}%"
        )
    if event_type == "perf_test.completed":
        return (
            f"性能测试完成 | RPS:{ctx.get('rps', 0)} "
            f"P95:{ctx.get('p95', 0)}ms 错误率:{ctx.get('error_rate', 0)}%"
        )
    # 未知事件类型：返回通用消息
    message = ctx.get("message", f"通知事件: {event_type}")
    return message if isinstance(message, str) else str(message)


# ---------------------------------------------------------------------------
# 各平台发送
# ---------------------------------------------------------------------------
def _build_text(title: str, content: str) -> str:
    """拼接标题与正文."""
    if title and content:
        return f"{title}\n{content}"
    return content or title or ""


def _runtime_webhook_url(stored_url: str) -> str:
    """Return a usable URL from encrypted or legacy plaintext storage."""
    plaintext = decrypt_url(stored_url)
    if not isinstance(plaintext, str) or not plaintext:
        raise ValueError("Webhook URL 未配置")
    return plaintext


async def send_feishu(
    webhook_url: str,
    secret: str | None,
    title: str,
    content: str,
) -> dict[str, Any]:
    """发送飞书机器人消息（支持加签）.

    消息格式: {"msg_type": "text", "content": {"text": "..."}}
    如有 secret: 请求体增加 timestamp 与 sign 字段。
    """
    payload: dict[str, Any] = {
        "msg_type": "text",
        "content": {"text": _build_text(title, content)},
    }
    if secret:
        timestamp = str(int(time.time()))
        sign = gen_feishu_sign(secret, timestamp)
        payload["timestamp"] = timestamp
        payload["sign"] = sign
    runtime_url = _runtime_webhook_url(webhook_url)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(runtime_url, json=payload)
        resp.raise_for_status()
        return {"ok": True, "status_code": resp.status_code, "text": resp.text}


async def send_dingtalk(
    webhook_url: str,
    secret: str | None,
    title: str,
    content: str,
) -> dict[str, Any]:
    """发送钉钉机器人消息（支持加签）.

    消息格式: {"msgtype": "text", "text": {"content": "..."}}
    如有 secret: URL 拼接 &timestamp=xxx&sign=base64(HmacSHA256(...))
    """
    payload: dict[str, Any] = {
        "msgtype": "text",
        "text": {"content": _build_text(title, content)},
    }
    runtime_url = _runtime_webhook_url(webhook_url)
    url = runtime_url
    if secret:
        timestamp = str(round(time.time() * 1000))
        sign = gen_dingtalk_sign(secret, timestamp)
        url = (
            f"{runtime_url}"
            f"&timestamp={quote_plus(timestamp)}"
            f"&sign={quote_plus(sign)}"
        )
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return {"ok": True, "status_code": resp.status_code, "text": resp.text}


async def send_wechat(
    webhook_url: str,
    title: str,
    content: str,
) -> dict[str, Any]:
    """发送企业微信群机器人消息.

    消息格式: {"msgtype": "text", "text": {"content": "..."}}
    """
    payload: dict[str, Any] = {
        "msgtype": "text",
        "text": {"content": _build_text(title, content)},
    }
    runtime_url = _runtime_webhook_url(webhook_url)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(runtime_url, json=payload)
        resp.raise_for_status()
        return {"ok": True, "status_code": resp.status_code, "text": resp.text}


async def send_slack(
    webhook_url: str,
    title: str,
    content: str,
) -> dict[str, Any]:
    """发送 Slack incoming webhook 消息.

    消息格式: {"text": "..."}
    """
    payload: dict[str, Any] = {"text": _build_text(title, content)}
    runtime_url = _runtime_webhook_url(webhook_url)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(runtime_url, json=payload)
        resp.raise_for_status()
        return {"ok": True, "status_code": resp.status_code, "text": resp.text}


# ---------------------------------------------------------------------------
# 统一发送入口
# ---------------------------------------------------------------------------
async def send_notification(
    channel: Any,
    event_type: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """根据渠道类型调用对应发送方法.

    channel 需包含属性: type, webhook_url, secret, name。
    返回: {"success": bool, "message": str}
    失败时捕获异常并返回失败信息，不抛出。
    """
    content = format_message(event_type, context)
    title = _EVENT_TITLES.get(event_type, "通知")
    ch_type = getattr(channel, "type", "")
    webhook_url = getattr(channel, "webhook_url", "")
    secret = getattr(channel, "secret", None)

    try:
        if ch_type == "feishu":
            await send_feishu(webhook_url, secret, title, content)
        elif ch_type == "dingtalk":
            await send_dingtalk(webhook_url, secret, title, content)
        elif ch_type == "wechat":
            await send_wechat(webhook_url, title, content)
        elif ch_type == "slack":
            await send_slack(webhook_url, title, content)
        else:
            return {
                "success": False,
                "message": f"不支持的渠道类型: {ch_type}",
            }
        return {"success": True, "message": content}
    except Exception as exc:  # noqa: BLE001
        safe_error = redact_url_from_text(str(exc), webhook_url)
        logger.warning(
            "通知发送失败 channel=%s event=%s: %s",
            getattr(channel, "name", "?"),
            event_type,
            safe_error,
        )
        return {
            "success": False,
            "message": safe_error,
        }
