"""失败归因自进化闭环服务."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.defect_pattern import DefectPattern
from app.models.test_case import TestCase
from app.schemas.execution import ExecutionResult
from app.services.ai_service import AIService
from app.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)


class SelfEvolutionService:
    """自进化闭环服务：失败 → 归因 → 提取模式 → 高频升级."""

    PROMOTE_THRESHOLD = 3  # 出现次数达到此值自动升级为业务规则

    def __init__(
        self,
        ai_service: AIService | None = None,
        knowledge_service: KnowledgeService | None = None,
    ):
        self.ai_service = ai_service or AIService()
        self.knowledge_service = knowledge_service or KnowledgeService()

    def handle_failure(
        self, case: TestCase, result: dict, db: Session
    ) -> dict | None:
        """执行失败时自动触发归因和模式提取.

        1. 调用 AI 归因（使用现有 analyze_failure 逻辑）
        2. 提取缺陷模式入库
        3. 如果出现次数达到阈值，自动升级为业务规则
        4. 返回 analysis 结果；无归因结果时返回 None
        """
        # 1. 构建 ExecutionResult 并调用 AI 归因
        exec_result = self._build_execution_result(case, result)
        try:
            analysis = self.ai_service.analyze_failure(exec_result)
        except Exception as exc:
            logger.warning("AI 归因调用失败: %s", exc)
            return None

        # 2. 无归因结果则不提取
        if not analysis or not analysis.get("root_cause"):
            return None

        # 3. 提取缺陷模式入库
        try:
            defect = self.knowledge_service.extract_defect_from_analysis(
                case, analysis, db
            )
        except Exception as exc:
            logger.warning("缺陷模式提取失败: %s", exc)
            return analysis

        # 4. 高频自动升级为业务规则
        if self._should_promote(defect):
            try:
                self.knowledge_service.promote_to_business_rule(defect, db)
            except Exception as exc:
                logger.warning("业务规则升级失败: %s", exc)

        return analysis

    def _should_promote(self, defect: DefectPattern) -> bool:
        """判断是否应该升级为业务规则."""
        return (
            defect.occurrence_count >= self.PROMOTE_THRESHOLD
            and defect.source == "ai_analysis"
        )

    def _build_execution_result(
        self, case: TestCase, result: dict
    ) -> ExecutionResult:
        """从字典构建 ExecutionResult，供 analyze_failure 使用."""
        return ExecutionResult(
            test_case_id=getattr(case, "id", "") or "",
            status=result.get("status", "failed"),
            duration=result.get("duration", 0.0),
            error_message=result.get("error_message"),
            error_traceback=result.get("error_traceback"),
        )
