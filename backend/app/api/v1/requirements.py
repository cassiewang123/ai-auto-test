"""需求管理 API（含文档导入与 AI 结构化管理）.

端点：
    GET    /requirements                          — 列表（支持筛选）
    GET    /requirements/stats                    — 统计
    POST   /requirements                          — 创建
    GET    /requirements/{id}                     — 详情
    PUT    /requirements/{id}                     — 更新
    DELETE /requirements/{id}                     — 删除
    POST   /requirements/{id}/documents           — 上传需求文档（PDF/DOCX/MD/TXT/图片）
    GET    /requirements/{id}/documents           — 需求文档列表
    DELETE /requirements/{id}/documents/{doc_id}  — 删除需求文档
    POST   /requirements/{id}/analyze             — 需求分析（功能清单/界面描述/待澄清项）
    GET    /requirements/{id}/analyses            — 历史分析结果
    GET    /requirements/analyses/{analysis_id}   — 单次分析详情
    POST   /requirements/analyses/{analysis_id}/messages — 对话补充指令并重新分析
    GET    /requirements/analyses/{analysis_id}/export   — 导出 Markdown
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.knowledge_base import KnowledgeBase
from app.models.requirement import Requirement
from app.models.requirement_document import (
    RequirementAnalysis,
    RequirementDocument,
)
from app.models.test_case import TestCase
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse, ResponseBase
from app.schemas.requirement import (
    RequirementCreate,
    RequirementResponse,
    RequirementStats,
    RequirementUpdate,
)
from app.schemas.test_design import (
    Clarification,
    FunctionItem,
    RequirementAnalysisMessageRequest,
    RequirementAnalysisRequest,
    RequirementAnalysisResponse,
    RequirementDocumentResponse,
    UiDescription,
)
from app.services.auth_service import get_current_user
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.requirement_analysis_service import (
    RequirementAnalysisResult,
    analyze_requirement,
)
from app.services.requirement_document_parser import (
    DocumentParseError,
    parse_document,
)

router = APIRouter()

_VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
_VALID_STATUSES = {"draft", "active", "covered", "archived"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

_knowledge_service = KnowledgeBaseService()


def _get_or_404(db: Session, requirement_id: str) -> Requirement:
    item = db.get(Requirement, requirement_id)
    if not item:
        raise NotFoundError("需求", requirement_id)
    return item


def _to_response(item: Requirement) -> RequirementResponse:
    data = RequirementResponse.model_validate(item)
    data.coverage = len(item.case_ids or [])
    return data


def _document_response(document: RequirementDocument) -> RequirementDocumentResponse:
    data = RequirementDocumentResponse.model_validate(document)
    data.char_count = len(document.content or "")
    data.warnings = list(document.warnings or [])
    return data


# ===========================================================================
# 需求 CRUD
# ===========================================================================
@router.get("", response_model=PageResponse[RequirementResponse])
def list_requirements(
    project_id: str | None = Query(None),
    status: str | None = Query(None),
    priority: str | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = select(Requirement)
    count_query = select(func.count()).select_from(Requirement)
    if project_id:
        query = query.where(Requirement.project_id == project_id)
        count_query = count_query.where(Requirement.project_id == project_id)
    if status:
        query = query.where(Requirement.status == status)
        count_query = count_query.where(Requirement.status == status)
    if priority:
        query = query.where(Requirement.priority == priority)
        count_query = count_query.where(Requirement.priority == priority)
    if keyword:
        pattern = f"%{keyword}%"
        query = query.where(Requirement.title.like(pattern))
        count_query = count_query.where(Requirement.title.like(pattern))

    total = db.execute(count_query).scalar_one()
    items = (
        db.execute(
            query.order_by(Requirement.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[RequirementResponse](
        data=[_to_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=DataResponse[RequirementStats])
def requirement_stats(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Requirement.status, func.count()).group_by(Requirement.status)
    ).all()
    counts = dict(rows)
    all_ids = db.execute(select(Requirement.case_ids)).scalars().all()
    total_cases = sum(len(ids or []) for ids in all_ids)
    return DataResponse[RequirementStats](
        data=RequirementStats(
            total=sum(counts.values()),
            draft=counts.get("draft", 0),
            active=counts.get("active", 0),
            covered=counts.get("covered", 0),
            archived=counts.get("archived", 0),
            total_cases=total_cases,
        )
    )


@router.post("", response_model=DataResponse[RequirementResponse])
def create_requirement(
    payload: RequirementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.priority not in _VALID_PRIORITIES:
        raise ValidationError(f"不支持的优先级: {payload.priority}")
    if payload.status not in _VALID_STATUSES:
        raise ValidationError(f"不支持的状态: {payload.status}")
    # 过滤掉不存在的用例 ID
    valid_case_ids: list[str] = []
    for case_id in payload.case_ids:
        if db.get(TestCase, case_id):
            valid_case_ids.append(case_id)

    item = Requirement(
        **payload.model_dump(exclude={"case_ids"}),
        case_ids=valid_case_ids,
        created_by=current_user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return DataResponse[RequirementResponse](data=_to_response(item))


@router.get("/{requirement_id}", response_model=DataResponse[RequirementResponse])
def get_requirement(requirement_id: str, db: Session = Depends(get_db)):
    return DataResponse[RequirementResponse](
        data=_to_response(_get_or_404(db, requirement_id))
    )


@router.put("/{requirement_id}", response_model=DataResponse[RequirementResponse])
def update_requirement(
    requirement_id: str,
    payload: RequirementUpdate,
    db: Session = Depends(get_db),
):
    item = _get_or_404(db, requirement_id)
    changes = payload.model_dump(exclude_unset=True)
    if "priority" in changes and changes["priority"] not in _VALID_PRIORITIES:
        raise ValidationError(f"不支持的优先级: {changes['priority']}")
    if "status" in changes and changes["status"] not in _VALID_STATUSES:
        raise ValidationError(f"不支持的状态: {changes['status']}")
    if "case_ids" in changes and changes["case_ids"] is not None:
        changes["case_ids"] = [
            case_id
            for case_id in changes["case_ids"]
            if db.get(TestCase, case_id)
        ]
    for key, value in changes.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return DataResponse[RequirementResponse](data=_to_response(item))


@router.delete("/{requirement_id}", response_model=DataResponse[dict])
def delete_requirement(requirement_id: str, db: Session = Depends(get_db)):
    item = _get_or_404(db, requirement_id)
    db.delete(item)
    db.commit()
    return DataResponse[dict](data={"deleted": True})


# ===========================================================================
# 需求文档
# ===========================================================================
@router.get(
    "/{requirement_id}/documents",
    response_model=DataResponse[list[RequirementDocumentResponse]],
)
def list_requirement_documents(
    requirement_id: str, db: Session = Depends(get_db)
):
    """需求附件文档列表."""
    _get_or_404(db, requirement_id)
    items = (
        db.execute(
            select(RequirementDocument)
            .where(RequirementDocument.requirement_id == requirement_id)
            .order_by(RequirementDocument.created_at.asc())
        )
        .scalars()
        .all()
    )
    return DataResponse[list[RequirementDocumentResponse]](
        data=[_document_response(item) for item in items]
    )


@router.post(
    "/{requirement_id}/documents",
    response_model=DataResponse[RequirementDocumentResponse],
)
async def upload_requirement_document(
    requirement_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传需求文档：支持 PDF / DOCX / MD / TXT / 图片，解析为正文文本."""
    _get_or_404(db, requirement_id)

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationError("文档超过 20MB 上限")

    try:
        parsed = parse_document(file.filename or "", data)
    except DocumentParseError as exc:
        raise ValidationError(str(exc)) from exc
    except Exception as exc:
        raise ValidationError(f"文档解析失败: {exc}") from exc

    document = RequirementDocument(
        requirement_id=requirement_id,
        filename=parsed.filename,
        file_type=parsed.file_type,
        file_size=parsed.file_size,
        content=parsed.content or None,
        warnings=parsed.warnings,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return DataResponse[RequirementDocumentResponse](
        data=_document_response(document)
    )


@router.delete(
    "/{requirement_id}/documents/{document_id}", response_model=ResponseBase
)
def delete_requirement_document(
    requirement_id: str, document_id: str, db: Session = Depends(get_db)
):
    """删除需求附件文档."""
    _get_or_404(db, requirement_id)
    document = db.get(RequirementDocument, document_id)
    if not document or document.requirement_id != requirement_id:
        raise NotFoundError("需求文档", document_id)
    db.delete(document)
    db.commit()
    return ResponseBase()


# ===========================================================================
# 需求分析
# ===========================================================================
def _collect_requirement_text(
    db: Session, requirement: Requirement, use_documents: bool = True
) -> str:
    """汇总需求正文：描述 + 验收标准 + 附件文档文本."""
    blocks: list[str] = []
    if requirement.description:
        blocks.append(requirement.description)
    if requirement.acceptance_criteria:
        blocks.append(f"验收标准：\n{requirement.acceptance_criteria}")
    if use_documents:
        documents = (
            db.execute(
                select(RequirementDocument).where(
                    RequirementDocument.requirement_id == requirement.id
                )
            )
            .scalars()
            .all()
        )
        for document in documents:
            content = (document.content or "").strip()
            if content:
                blocks.append(f"【附件：{document.filename}】\n{content}")
    return "\n\n".join(blocks).strip()


def _build_analysis(
    db: Session,
    requirement: Requirement,
    result: RequirementAnalysisResult,
    knowledge_base_id: str | None,
    messages: list[dict],
    creator_id: str | None,
) -> RequirementAnalysis:
    analysis = RequirementAnalysis(
        requirement_id=requirement.id,
        engine=result.engine,
        knowledge_base_id=knowledge_base_id,
        function_items=result.function_items,
        ui_descriptions=result.ui_descriptions,
        clarifications=result.clarifications,
        markdown=result.to_dict()["markdown"],
        messages=messages,
        created_by=creator_id,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def _analysis_response(
    db: Session, analysis: RequirementAnalysis
) -> RequirementAnalysisResponse:
    data = RequirementAnalysisResponse.model_validate(analysis)
    # 显式构造成强类型模型，避免裸 dict 触发 Pydantic 序列化告警
    data.function_items = [
        FunctionItem(
            module=str(item.get("module") or ""),
            points=[
                str(point)
                for point in (
                    item.get("points")
                    if isinstance(item.get("points"), list)
                    else [item.get("points")]
                )
                if point
            ],
        )
        for item in (analysis.function_items or [])
        if isinstance(item, dict)
    ]
    data.ui_descriptions = [
        UiDescription(
            page=str(item.get("page") or ""),
            description=str(item.get("description") or ""),
        )
        for item in (analysis.ui_descriptions or [])
        if isinstance(item, dict)
    ]
    data.clarifications = [
        Clarification(
            question=str(item.get("question") or ""),
            reason=str(item.get("reason") or ""),
        )
        for item in (analysis.clarifications or [])
        if isinstance(item, dict)
    ]
    data.messages = list(analysis.messages or [])
    return data


@router.post(
    "/{requirement_id}/analyze",
    response_model=DataResponse[RequirementAnalysisResponse],
)
def analyze(
    requirement_id: str,
    payload: RequirementAnalysisRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """对需求做结构化分析，输出功能清单 / 界面描述 / 待澄清项."""
    requirement = _get_or_404(db, requirement_id)
    payload = payload or RequirementAnalysisRequest()

    text = _collect_requirement_text(db, requirement, payload.use_documents)
    if not text.strip():
        raise ValidationError("需求暂无正文，请先填写描述或上传需求文档")

    knowledge_context = ""
    if payload.knowledge_base_id:
        if not db.get(KnowledgeBase, payload.knowledge_base_id):
            raise NotFoundError("知识库", payload.knowledge_base_id)
        knowledge_context, _ = _knowledge_service.retrieve_for_prompt(
            db,
            payload.knowledge_base_id,
            f"{requirement.title}\n{text[:2000]}",
        )

    query_text = text
    if payload.question:
        # 对话窗口中追加的要求参与分析，实现「补充、调整或重新梳理」
        query_text = f"{text}\n\n测试人员补充要求：{payload.question}"

    result = analyze_requirement(
        title=requirement.title,
        text=query_text,
        knowledge_context=knowledge_context,
    )

    messages: list[dict] = []
    if payload.question:
        messages.append({"role": "user", "content": payload.question})
    messages.append(
        {
            "role": "assistant",
            "content": "已完成分析，可直接编辑修改结果。",
            "kind": "analysis",
        }
    )

    analysis = _build_analysis(
        db,
        requirement,
        result,
        payload.knowledge_base_id,
        messages,
        current_user.id,
    )
    return DataResponse[RequirementAnalysisResponse](
        data=_analysis_response(db, analysis)
    )


@router.get(
    "/{requirement_id}/analyses",
    response_model=DataResponse[list[RequirementAnalysisResponse]],
)
def list_analyses(requirement_id: str, db: Session = Depends(get_db)):
    """该需求的历史分析结果（最新在前）."""
    _get_or_404(db, requirement_id)
    items = (
        db.execute(
            select(RequirementAnalysis)
            .where(RequirementAnalysis.requirement_id == requirement_id)
            .order_by(RequirementAnalysis.created_at.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )
    return DataResponse[list[RequirementAnalysisResponse]](
        data=[_analysis_response(db, item) for item in items]
    )


@router.get(
    "/analyses/{analysis_id}", response_model=DataResponse[RequirementAnalysisResponse]
)
def get_analysis(analysis_id: str, db: Session = Depends(get_db)):
    """单次分析详情."""
    analysis = db.get(RequirementAnalysis, analysis_id)
    if not analysis:
        raise NotFoundError("需求分析", analysis_id)
    return DataResponse[RequirementAnalysisResponse](
        data=_analysis_response(db, analysis)
    )


@router.post(
    "/analyses/{analysis_id}/messages",
    response_model=DataResponse[RequirementAnalysisResponse],
)
def continue_analysis(
    analysis_id: str,
    payload: RequirementAnalysisMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """在对话窗口追加指令，基于同一需求重新分析（保留对话历史）."""
    previous = db.get(RequirementAnalysis, analysis_id)
    if not previous:
        raise NotFoundError("需求分析", analysis_id)
    requirement = _get_or_404(db, previous.requirement_id)

    text = _collect_requirement_text(db, requirement, use_documents=True)
    knowledge_context = ""
    if previous.knowledge_base_id:
        knowledge_context, _ = _knowledge_service.retrieve_for_prompt(
            db,
            previous.knowledge_base_id,
            f"{requirement.title}\n{text[:2000]}",
        )

    combined_text = (
        f"{text}\n\n测试人员补充要求：{payload.message}"
    )
    result = analyze_requirement(
        title=requirement.title,
        text=combined_text,
        knowledge_context=knowledge_context,
    )

    messages = list(previous.messages or [])
    messages.append({"role": "user", "content": payload.message})
    messages.append(
        {
            "role": "assistant",
            "content": "已根据补充要求更新分析结果。",
            "kind": "analysis",
        }
    )
    previous.function_items = result.function_items
    previous.ui_descriptions = result.ui_descriptions
    previous.clarifications = result.clarifications
    previous.markdown = result.to_dict()["markdown"]
    previous.messages = messages
    previous.engine = result.engine
    previous.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(previous)
    return DataResponse[RequirementAnalysisResponse](
        data=_analysis_response(db, previous)
    )


@router.get("/analyses/{analysis_id}/export", response_class=PlainTextResponse)
def export_analysis(analysis_id: str, db: Session = Depends(get_db)):
    """导出分析结果为 Markdown 文档."""
    analysis = db.get(RequirementAnalysis, analysis_id)
    if not analysis:
        raise NotFoundError("需求分析", analysis_id)
    requirement = db.get(Requirement, analysis.requirement_id)
    title = requirement.title if requirement else "需求分析"
    content = analysis.markdown or ""
    body = f"# 需求分析：{title}\n\n{content}"
    filename = f"requirement-analysis-{analysis_id}.md"
    return PlainTextResponse(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )
