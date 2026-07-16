"""审计日志服务 (SEC-09).

提供 log_audit 写入接口与 sanitize_dict 脱敏工具。
敏感字段（password / secret / token / cookie / api_key / private_key）
在写入审计日志前自动替换为 ****。
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

# 需要脱敏的敏感字段名（小写匹配）
SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "cookie",
    "api_key",
    "private_key",
}


def sanitize_dict(d: dict) -> dict:
    """脱敏字典中的敏感字段。

    递归处理嵌套字典，将 key 包含敏感词的字段值替换为 ****。
    """
    if not isinstance(d, dict):
        return d

    result: dict = {}
    for k, v in d.items():
        key_lower = k.lower()
        if key_lower in SENSITIVE_KEYS or any(s in key_lower for s in SENSITIVE_KEYS):
            result[k] = "****"
        elif isinstance(v, dict):
            result[k] = sanitize_dict(v)
        else:
            result[k] = v
    return result


def log_audit(
    db: Session,
    actor_id: str | None = None,
    actor_name: str | None = None,
    action: str = "",
    resource_type: str = "",
    resource_id: str | None = None,
    project_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    result: str = "success",
    error_message: str | None = None,
    source_ip: str | None = None,
    request_id: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """写入一条审计日志。

    before / after 字段在写入前经过 sanitize_dict 脱敏处理，
    确保敏感信息不会出现在审计日志中。
    """
    log = AuditLog(
        actor_id=actor_id,
        actor_name=actor_name,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        project_id=project_id,
        request_id=request_id,
        source_ip=source_ip,
        user_agent=user_agent,
        before=json.dumps(sanitize_dict(before), ensure_ascii=False) if before else None,
        after=json.dumps(sanitize_dict(after), ensure_ascii=False) if after else None,
        result=result,
        error_message=error_message,
    )
    db.add(log)
    db.commit()
    return log
