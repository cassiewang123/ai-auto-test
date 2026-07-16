"""失败归因自进化闭环服务测试."""
from __future__ import annotations

from unittest.mock import MagicMock

import app.models  # noqa: F401  注册已有模型元数据
from app.models.business_rule import BusinessRule  # noqa: F401
from app.models.defect_pattern import DefectPattern  # noqa: F401
from app.models.test_case import TestCase
from app.services.self_evolution import SelfEvolutionService

MOCK_ANALYSIS = {
    "root_cause": "token 过期",
    "evidence": "401 Unauthorized",
    "category": "auth",
    "suggestion": "刷新 token",
    "confidence": 0.9,
}

FAILED_RESULT = {
    "status": "failed",
    "duration": 1.5,
    "error_message": "Assertion failed",
}


def _make_case(db_session) -> TestCase:
    """创建并保存一个测试用例."""
    case = TestCase(title="登录测试", method="POST", url="/api/login")
    db_session.add(case)
    db_session.commit()
    return case


def _make_service(analysis_return) -> SelfEvolutionService:
    """构造注入 mock AIService 的 SelfEvolutionService."""
    mock_ai = MagicMock()
    mock_ai.analyze_failure.return_value = analysis_return
    return SelfEvolutionService(ai_service=mock_ai)


# ---------------------------------------------------------------------------
# 失败归因 → 提取缺陷模式
# ---------------------------------------------------------------------------
class TestHandleFailure:
    def test_handle_failure_extracts_pattern(self, db_session):
        """失败时提取缺陷模式."""
        case = _make_case(db_session)
        service = _make_service(MOCK_ANALYSIS)

        analysis = service.handle_failure(case, FAILED_RESULT, db_session)

        assert analysis is not None
        assert analysis["root_cause"] == "token 过期"

        defects = db_session.query(DefectPattern).all()
        assert len(defects) == 1
        assert defects[0].title == "token 过期"
        assert defects[0].pattern_type == "auth"
        assert defects[0].source == "ai_analysis"
        assert defects[0].related_case_id == case.id
        assert defects[0].occurrence_count == 1

    def test_handle_failure_accumulates_count(self, db_session):
        """相同模式累加出现次数."""
        case = _make_case(db_session)
        service = _make_service(MOCK_ANALYSIS)

        # 第一次失败
        service.handle_failure(case, FAILED_RESULT, db_session)
        defects = db_session.query(DefectPattern).all()
        assert len(defects) == 1
        assert defects[0].occurrence_count == 1

        # 第二次失败（相同根因）
        service.handle_failure(case, FAILED_RESULT, db_session)
        db_session.expire_all()
        defects = db_session.query(DefectPattern).all()
        assert len(defects) == 1  # 不新建，累加
        assert defects[0].occurrence_count == 2

    def test_handle_failure_promotes_high_frequency(self, db_session):
        """出现次数达到阈值时自动升级为业务规则."""
        case = _make_case(db_session)
        service = _make_service(MOCK_ANALYSIS)

        # 调用 3 次（PROMOTE_THRESHOLD = 3），第 3 次应触发升级
        for _ in range(3):
            service.handle_failure(case, FAILED_RESULT, db_session)

        # 验证缺陷模式
        db_session.expire_all()
        defects = db_session.query(DefectPattern).all()
        assert len(defects) == 1
        assert defects[0].occurrence_count == 3

        # 验证业务规则已自动创建
        rules = db_session.query(BusinessRule).all()
        assert len(rules) == 1
        assert rules[0].source == "defect_promoted"
        assert rules[0].related_defect_id == defects[0].id
        assert "token 过期" in rules[0].title

    def test_handle_failure_no_analysis(self, db_session):
        """无归因结果时不提取缺陷模式."""
        case = _make_case(db_session)
        service = _make_service(None)

        result = service.handle_failure(case, FAILED_RESULT, db_session)

        assert result is None
        assert db_session.query(DefectPattern).count() == 0

    def test_handle_failure_empty_analysis(self, db_session):
        """归因结果无 root_cause 时不提取."""
        case = _make_case(db_session)
        service = _make_service({"root_cause": "", "category": "unknown"})

        result = service.handle_failure(case, FAILED_RESULT, db_session)

        assert result is None
        assert db_session.query(DefectPattern).count() == 0
