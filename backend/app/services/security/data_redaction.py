"""Recursive credential redaction for API responses and persisted snapshots."""

from __future__ import annotations

import re
from typing import Any

REDACTED_VALUE = "****"

_SENSITIVE_KEYS = {
    "authorization",
    "proxy_authorization",
    "cookie",
    "set_cookie",
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "api_key",
    "apikey",
    "x_api_key",
}
_COOKIE_CONTAINER_KEYS = {"cookies", "session_cookies"}
_NON_SECRET_METADATA_SUFFIXES = {"_count", "_masked", "_prefix", "_total", "_usage"}
_INLINE_AUTHORIZATION = re.compile(r"(?i)(authorization\s*[:=]\s*)[^\r\n,]+")
_INLINE_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")
_INLINE_COOKIE = re.compile(r"(?i)((?:set-)?cookie\s*[:=]\s*)[^\r\n]+")


def _normalized_key(key: Any) -> str:
    return str(key).strip().lower().replace("-", "_")


def _is_sensitive_key(key: Any, *, transport_only: bool = False) -> bool:
    normalized = _normalized_key(key)
    if normalized.startswith("has_") or any(normalized.endswith(suffix) for suffix in _NON_SECRET_METADATA_SUFFIXES):
        return False
    if transport_only:
        return normalized in {
            "authorization",
            "proxy_authorization",
            "cookie",
            "set_cookie",
        } or normalized.endswith(("_authorization", "_cookie"))
    return normalized in _SENSITIVE_KEYS or normalized.endswith(("_password", "_secret", "_token", "_cookie"))


def _redact_inline_text(value: str) -> str:
    redacted = _INLINE_AUTHORIZATION.sub(rf"\1{REDACTED_VALUE}", value)
    redacted = _INLINE_BEARER.sub(rf"\1{REDACTED_VALUE}", redacted)
    return _INLINE_COOKIE.sub(rf"\1{REDACTED_VALUE}", redacted)


def redact_sensitive_data(
    value: Any,
    *,
    parent_key: str | None = None,
    transport_only: bool = False,
) -> Any:
    """Recursively redact credentials without mutating the source object."""
    parent = _normalized_key(parent_key) if parent_key else ""
    if isinstance(value, dict):
        cookie_container = parent in _COOKIE_CONTAINER_KEYS
        cookie_record = cookie_container and "value" in value
        named_secret_record = (
            "name" in value
            and "value" in value
            and _is_sensitive_key(
                value.get("name"),
                transport_only=transport_only,
            )
        )
        result: dict[Any, Any] = {}
        for key, item in value.items():
            normalized = _normalized_key(key)
            if (
                _is_sensitive_key(key, transport_only=transport_only)
                or (cookie_record and normalized == "value")
                or (named_secret_record and normalized == "value")
                or (cookie_container and not cookie_record)
            ):
                result[key] = REDACTED_VALUE
            else:
                result[key] = redact_sensitive_data(
                    item,
                    parent_key=normalized,
                    transport_only=transport_only,
                )
        return result
    if isinstance(value, list):
        return [
            redact_sensitive_data(
                item,
                parent_key=parent,
                transport_only=transport_only,
            )
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            redact_sensitive_data(
                item,
                parent_key=parent,
                transport_only=transport_only,
            )
            for item in value
        )
    if isinstance(value, str):
        return _redact_inline_text(value)
    return value
