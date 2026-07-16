"""知识工程 API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.business_rule import BusinessRule
from app.models.defect_pattern import DefectPattern
from app.models.interface_knowledge import InterfaceKnowledge
from app.models.test_case import TestCase
from app.models.test_result import TestResult
from app.schemas.common import DataResponse, PageResponse, ResponseBase
from app.schemas.knowledge import (
    BusinessRuleCreate,
    BusinessRuleResponse,
    BusinessRuleUpdate,
    DefectPatternCreate,
    DefectPatternResponse,
    DefectPatternUpdate,
    InterfaceKnowledgeCreate,
    InterfaceKnowledgeResponse,
    InterfaceKnowledgeUpdate,
)
from app.services.knowledge_service import KnowledgeService

router = APIRouter()
_service = KnowledgeService()


# ===========================================================================
# 缺陷模式 DefectPattern
# ===========================================================================
def _get_defect_or_404(db: Session, defect_id: str) -> DefectPattern:
    defect = db.get(DefectPattern, defect_id)
    if not defect:
        raise NotFoundError("缺陷模式", defect_id)
    return defect


@router.get("/defects", response_model=PageResponse[DefectPatternResponse])
def list_defects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None, description="按项目筛选"),
    pattern_type: str | None = Query(None, description="按缺陷类型筛选"),
    db: Session = Depends(get_db),
):
    """缺陷模式列表分页."""
    query = select(DefectPattern)
    count_q = select(func.count()).select_from(DefectPattern)
    if project_id:
        query = query.where(DefectPattern.project_id == project_id)
        count_q = count_q.where(DefectPattern.project_id == project_id)
    if pattern_type:
        query = query.where(DefectPattern.pattern_type == pattern_type)
        count_q = count_q.where(DefectPattern.pattern_type == pattern_type)

    total = db.execute(count_q).scalar_one()
    items = (
        db.execute(
            query.order_by(DefectPattern.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[DefectPatternResponse](
        data=items, total=total, page=page, page_size=page_size
    )


@router.post("/defects", response_model=DataResponse[DefectPatternResponse])
def create_defect(payload: DefectPatternCreate, db: Session = Depends(get_db)):
    """手动创建缺陷模式."""
    defect = DefectPattern(**payload.model_dump())
    db.add(defect)
    db.commit()
    db.refresh(defect)
    return DataResponse[DefectPatternResponse](data=defect)


@router.post("/defects/extract", response_model=DataResponse[DefectPatternResponse])
def extract_defect(
    test_result_id: str = Query(..., description="TestResult ID"),
    db: Session = Depends(get_db),
):
    """从指定 TestResult 的 AI 归因结果中提取缺陷模式."""
    result = db.get(TestResult, test_result_id)
    if not result:
        raise NotFoundError("TestResult", test_result_id)

    analysis = result.ai_analysis
    if not analysis:
        raise NotFoundError("AI分析结果", test_result_id)

    case = db.get(TestCase, result.test_case_id) if result.test_case_id else None
    defect = _service.extract_defect_from_analysis(case, analysis, db)
    return DataResponse[DefectPatternResponse](data=defect)


@router.put("/defects/{defect_id}", response_model=DataResponse[DefectPatternResponse])
def update_defect(
    defect_id: str,
    payload: DefectPatternUpdate,
    db: Session = Depends(get_db),
):
    """更新缺陷模式."""
    defect = _get_defect_or_404(db, defect_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(defect, field, value)
    db.commit()
    db.refresh(defect)
    return DataResponse[DefectPatternResponse](data=defect)


@router.delete("/defects/{defect_id}", response_model=ResponseBase)
def delete_defect(defect_id: str, db: Session = Depends(get_db)):
    """删除缺陷模式."""
    defect = _get_defect_or_404(db, defect_id)
    db.delete(defect)
    db.commit()
    return ResponseBase()


# ===========================================================================
# 业务规则 BusinessRule
# ===========================================================================
def _get_rule_or_404(db: Session, rule_id: str) -> BusinessRule:
    rule = db.get(BusinessRule, rule_id)
    if not rule:
        raise NotFoundError("业务规则", rule_id)
    return rule


@router.get("/rules", response_model=PageResponse[BusinessRuleResponse])
def list_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None, description="按项目筛选"),
    rule_type: str | None = Query(None, description="按规则类型筛选"),
    db: Session = Depends(get_db),
):
    """业务规则列表分页."""
    query = select(BusinessRule)
    count_q = select(func.count()).select_from(BusinessRule)
    if project_id:
        query = query.where(BusinessRule.project_id == project_id)
        count_q = count_q.where(BusinessRule.project_id == project_id)
    if rule_type:
        query = query.where(BusinessRule.rule_type == rule_type)
        count_q = count_q.where(BusinessRule.rule_type == rule_type)

    total = db.execute(count_q).scalar_one()
    items = (
        db.execute(
            query.order_by(BusinessRule.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[BusinessRuleResponse](
        data=items, total=total, page=page, page_size=page_size
    )


@router.post("/rules", response_model=DataResponse[BusinessRuleResponse])
def create_rule(payload: BusinessRuleCreate, db: Session = Depends(get_db)):
    """手动创建业务规则."""
    rule = BusinessRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return DataResponse[BusinessRuleResponse](data=rule)


@router.post("/rules/promote", response_model=DataResponse[dict])
def promote_rules(
    threshold: int = Query(3, ge=1, description="出现次数阈值"),
    db: Session = Depends(get_db),
):
    """将高频缺陷模式（出现次数 > threshold）自动升级为业务规则."""
    defects = (
        db.execute(
            select(DefectPattern).where(
                DefectPattern.occurrence_count > threshold
            )
        )
        .scalars()
        .all()
    )
    promoted_ids: list[str] = []
    for defect in defects:
        rule = _service.promote_to_business_rule(defect, db)
        promoted_ids.append(rule.id)
    return DataResponse(
        data={"promoted_count": len(promoted_ids), "rule_ids": promoted_ids}
    )


@router.put("/rules/{rule_id}", response_model=DataResponse[BusinessRuleResponse])
def update_rule(
    rule_id: str,
    payload: BusinessRuleUpdate,
    db: Session = Depends(get_db),
):
    """更新业务规则."""
    rule = _get_rule_or_404(db, rule_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return DataResponse[BusinessRuleResponse](data=rule)


@router.delete("/rules/{rule_id}", response_model=ResponseBase)
def delete_rule(rule_id: str, db: Session = Depends(get_db)):
    """删除业务规则."""
    rule = _get_rule_or_404(db, rule_id)
    db.delete(rule)
    db.commit()
    return ResponseBase()


# ===========================================================================
# 接口知识 InterfaceKnowledge
# ===========================================================================
def _get_interface_or_404(db: Session, knowledge_id: str) -> InterfaceKnowledge:
    item = db.get(InterfaceKnowledge, knowledge_id)
    if not item:
        raise NotFoundError("接口知识", knowledge_id)
    return item


@router.get("/interfaces", response_model=PageResponse[InterfaceKnowledgeResponse])
def list_interfaces(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None, description="按项目筛选"),
    db: Session = Depends(get_db),
):
    """接口知识列表分页."""
    query = select(InterfaceKnowledge)
    count_q = select(func.count()).select_from(InterfaceKnowledge)
    if project_id:
        query = query.where(InterfaceKnowledge.project_id == project_id)
        count_q = count_q.where(InterfaceKnowledge.project_id == project_id)

    total = db.execute(count_q).scalar_one()
    items = (
        db.execute(
            query.order_by(InterfaceKnowledge.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[InterfaceKnowledgeResponse](
        data=items, total=total, page=page, page_size=page_size
    )


@router.post("/interfaces", response_model=DataResponse[InterfaceKnowledgeResponse])
def create_interface(
    payload: InterfaceKnowledgeCreate, db: Session = Depends(get_db)
):
    """创建接口知识."""
    item = InterfaceKnowledge(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return DataResponse[InterfaceKnowledgeResponse](data=item)


@router.put(
    "/interfaces/{knowledge_id}",
    response_model=DataResponse[InterfaceKnowledgeResponse],
)
def update_interface(
    knowledge_id: str,
    payload: InterfaceKnowledgeUpdate,
    db: Session = Depends(get_db),
):
    """更新接口知识."""
    item = _get_interface_or_404(db, knowledge_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return DataResponse[InterfaceKnowledgeResponse](data=item)


@router.delete("/interfaces/{knowledge_id}", response_model=ResponseBase)
def delete_interface(knowledge_id: str, db: Session = Depends(get_db)):
    """删除接口知识."""
    item = _get_interface_or_404(db, knowledge_id)
    db.delete(item)
    db.commit()
    return ResponseBase()


# ===========================================================================
# RAG 检索
# ===========================================================================
@router.post("/search", response_model=DataResponse[dict])
def search_knowledge(
    query: str = Query(..., description="搜索关键词"),
    project_id: str | None = Query(None, description="项目ID筛选"),
    db: Session = Depends(get_db),
):
    """RAG 检索：输入关键词，召回相关知识."""
    knowledge = _service.search_knowledge(query, project_id, db)
    return DataResponse(data=knowledge)
