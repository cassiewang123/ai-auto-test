"""AI 增强 API 路由。

端点：
- POST /ai/generate-test-case   生成测试用例代码
- POST /ai/recommend-assertions 推荐断言规则
- POST /ai/analyze-failure      分析失败用例

通过依赖注入 AIService 实例，便于测试时替换。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.test_case import AssertionRule, TestCase
from app.schemas.execution import ExecutionResult
from app.services.ai_service import AIService

router = APIRouter()


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class GenerateTestCaseRequest(BaseModel):
    """生成测试用例请求。"""

    description: str
    api_schema: dict | None = None


class RecommendAssertionsRequest(BaseModel):
    """推荐断言请求。"""

    response_sample: dict


# ---------------------------------------------------------------------------
# 依赖
# ---------------------------------------------------------------------------
def get_ai_service() -> AIService:
    """提供 AIService 实例的依赖工厂。"""
    return AIService()


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@router.post("/generate-test-case")
def generate_test_case(
    request: GenerateTestCaseRequest,
    service: AIService = Depends(get_ai_service),
) -> dict:
    """根据自然语言描述生成 PyTest 用例代码。"""
    code = service.generate_test_case(
        description=request.description, api_schema=request.api_schema
    )
    return {"code": 0, "message": "ok", "data": {"code": code}}


@router.post("/recommend-assertions")
def recommend_assertions(
    request: RecommendAssertionsRequest,
    service: AIService = Depends(get_ai_service),
) -> dict:
    """分析响应结构，推荐断言规则。"""
    assertions = service.recommend_assertions(request.response_sample)
    return {"code": 0, "message": "ok", "data": {"assertions": assertions}}


@router.post("/analyze-failure")
def analyze_failure(
    result: ExecutionResult,
    service: AIService = Depends(get_ai_service),
) -> dict:
    """分析失败用例，返回根因分析结果。"""
    analysis = service.analyze_failure(result)
    return {"code": 0, "message": "ok", "data": analysis}


# ---------------------------------------------------------------------------
# 结构化用例生成与导入
# ---------------------------------------------------------------------------
class GenerateStructuredCasesRequest(BaseModel):
    """批量生成结构化用例请求."""

    source_type: str  # interface | har | description
    source_data: dict  # interface_ids / har_content / description
    options: dict = {}  # case_types, max_cases, include_assertions


class ImportCasesRequest(BaseModel):
    """导入结构化用例请求."""

    cases: list[dict]  # 预览后选中的用例
    project_id: str | None = None


@router.post("/generate-test-cases")
def generate_structured_cases(
    request: GenerateStructuredCasesRequest,
    db: Session = Depends(get_db),
    service: AIService = Depends(get_ai_service),
) -> dict:
    """批量生成结构化测试用例，返回预览列表（不入库）."""
    cases = asyncio.run(
        service.generate_structured_cases(
            source_type=request.source_type,
            source_data=request.source_data,
            options=request.options,
        )
    )
    return {
        "code": 0,
        "message": "ok",
        "data": {"cases": cases, "total": len(cases)},
    }


@router.post("/import-cases")
def import_cases(
    request: ImportCasesRequest,
    db: Session = Depends(get_db),
) -> dict:
    """将选中的结构化用例批量入库.

    创建 TestCase 记录并级联创建 AssertionRule。
    """
    created_ids: list[str] = []
    for case_data in request.cases:
        data = dict(case_data)
        assertions_data = data.pop("assertions", []) or []
        priority = data.pop("priority", "P1")
        data.pop("case_type", None)  # 非 TestCase 字段

        case = TestCase(
            title=data.get("title", "未命名用例"),
            method=data.get("method", "GET"),
            url=data.get("url", "/api/v1/endpoint"),
            headers=data.get("headers", {}),
            params=data.get("params", {}),
            body=data.get("body"),
            markers=data.get("markers", ["ai-generated"]),
            description=data.get("description"),
            group_path=data.get("group_path"),
            project_id=request.project_id or data.get("project_id"),
        )
        db.add(case)
        db.flush()

        for a in assertions_data:
            expected = a.get("expected")
            assertion = AssertionRule(
                test_case_id=case.id,
                assertion_type=a.get("type", a.get("assertion_type", "status_code")),
                expression=a.get("expression"),
                operator=a.get("operator", "eq"),
                expected=str(expected) if expected is not None else None,
                priority=a.get("priority", priority),
                order=a.get("order", 0),
            )
            db.add(assertion)

        created_ids.append(case.id)

    db.commit()

    return {
        "code": 0,
        "message": "ok",
        "data": {"created_count": len(created_ids), "case_ids": created_ids},
    }
