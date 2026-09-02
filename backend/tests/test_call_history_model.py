"""CallHistory 模型约束测试.

聚焦验证 call_history 的请求体/响应体等字段可为空，避免 NOT NULL 约束
在「无请求体（GET / quick_test）」场景下阻断落库。
"""
from __future__ import annotations

from app.models.call_history import CallHistory


class TestCallHistoryNullability:
    def test_record_without_request_body_can_persist(self, db_session):
        """无请求体（body 为空）的历史记录应能成功保存。

        回归修复：body 原先声明为非空导致插入 body=None 抛出
        sqlite3.IntegrityError: NOT NULL constraint failed: call_history.body。
        """
        call = CallHistory(
            id="history-call-no-body",
            method="GET",
            url="https://example.test/health",
            status="passed",
            duration=0.5,
            source="quick_test",
            project_id=None,
            created_by="test-admin-id",
        )
        db_session.add(call)
        db_session.commit()
        db_session.refresh(call)
        assert call.id == "history-call-no-body"
        assert call.body is None

    def test_record_with_request_body_keeps_value(self, db_session):
        """带请求体的历史记录应保留 body 内容。"""
        call = CallHistory(
            id="history-call-with-body",
            method="POST",
            url="https://example.test/login",
            status="passed",
            duration=0.5,
            source="quick_test",
            project_id=None,
            created_by="test-admin-id",
            body={"username": "admin"},
        )
        db_session.add(call)
        db_session.commit()
        db_session.refresh(call)
        assert call.body == {"username": "admin"}