"""AI 测试用例生成 API：会话、测试点确认、用例草稿与写入用例库.

端点：
    POST   /test-design/sessions                      — 创建生成会话
    GET    /test-design/sessions                      — 会话列表
    GET    /test-design/sessions/{id}                 — 会话详情（含测试点与用例）
    DELETE /test-design/sessions/{id}                 — 删除会话
    POST   /test-design/sessions/{id}/messages        — 继续对话（补充信息）
    POST   /test-design/sessions/{id}/generate-points — 生成待确认测试点
    PUT    /test-design/sessions/{id}/points          — 批量修改/勾选测试点
    POST   /test-design/sessions/{id}/generate-cases  — 基于已确认测试点生成用例
    POST   /test-design/sessions/{id}/review          — 多维度评审
    POST   /test-design/sessions/{id}/import-cases    — 写入用例库
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.api_case_record import ApiCaseRecord
from app.models.functional_test_case import FunctionalTestCase
from app.models.knowledge_base import KnowledgeBase
from app.models.requirement import Requirement
from app.models.requirement_document import (
    RequirementAnalysis,
    RequirementDocument,
)
from app.models.test_design import (
    GeneratedCase,
    GeneratedTestPoint,
    TestDesignSession,
)
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse, ResponseBase
from app.schemas.test_design import (
    GenerateCasesRequest,
    GeneratedCaseItem,
    ImportCasesRequest,
    ImportCasesResponse,
    ReviewRequest,
    ReviewResponse,
    SessionMessageRequest,
    TestDesignSessionCreate,
    TestDesignSessionResponse,
    TestPointBulkUpdateRequest,
    TestPointItem,
)
from app.services.auth_service import get_current_user
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.requirement_document_parser import (
    extract_image_data_urls,
    strip_image_markers,
)
from app.services.test_design_service import (
    DEFAULT_REVIEW_DIMENSIONS,
    MODE_API,
    MODE_MANUAL,
    VALID_OUTPUT_MODES,
    CaseDraft,
    TestPointDraft,
    build_questions,
    generate_cases,
    generate_test_points,
    review_cases,
)

router = APIRouter()

_VALID_MODES = {"quick", "stepwise"}
_MAX_DIMENSION_WEIGHT = 5
_knowledge_service = KnowledgeBaseService()

# 用例分类 -> 接口用例库的场景类型
_API_CASE_TYPE_BY_CATEGORY = {
    "功能": "normal",
    "异常": "exception",
    "边界": "boundary",
    "权限": "permission",
    "安全": "permission",
}


# ===========================================================================
# 内部辅助
# ===========================================================================
def _get_session_or_404(db: Session, session_id: str) -> TestDesignSession:
    item = db.get(TestDesignSession, session_id)
    if not item:
        raise NotFoundError("AI 测试设计会话", session_id)
    return item


def _requirement_text(db: Session, requirement_id: str | None) -> str:
    """取需求正文（描述 + 验收标准 + 附件文档）."""
    if not requirement_id:
        return ""
    requirement = db.get(Requirement, requirement_id)
    if not requirement:
        return ""
    blocks: list[str] = []
    if requirement.description:
        blocks.append(requirement.description)
    if requirement.acceptance_criteria:
        blocks.append(f"验收标准：\n{requirement.acceptance_criteria}")
    documents = (
        db.execute(
            select(RequirementDocument).where(
                RequirementDocument.requirement_id == requirement_id
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


def _latest_analysis(db: Session, requirement_id: str | None) -> RequirementAnalysis | None:
    """取该需求最近一次分析结果，用于复用功能清单与待澄清项."""
    if not requirement_id:
        return None
    return (
        db.execute(
            select(RequirementAnalysis)
            .where(RequirementAnalysis.requirement_id == requirement_id)
            .order_by(RequirementAnalysis.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def _normalize_dimensions(raw: dict[str, Any] | None) -> dict[str, int]:
    """把评审维度权重规整为 1-5 的整数，未知维度忽略."""
    if not raw:
        return dict(DEFAULT_REVIEW_DIMENSIONS)
    normalized: dict[str, int] = {}
    for name, weight in raw.items():
        if name not in DEFAULT_REVIEW_DIMENSIONS:
            continue
        try:
            value = int(weight)
        except (TypeError, ValueError):
            continue
        normalized[name] = max(1, min(_MAX_DIMENSION_WEIGHT, value))
    return normalized or dict(DEFAULT_REVIEW_DIMENSIONS)


def _session_response(
    db: Session, session: TestDesignSession
) -> TestDesignSessionResponse:
    data = TestDesignSessionResponse.model_validate(session)
    data.review_dimensions = dict(session.review_dimensions or {})
    data.messages = list(session.messages or [])
    data.knowledge_refs = list(session.knowledge_refs or [])
    data.case_ids = list(session.case_ids or [])
    data.output_mode = session.output_mode or MODE_MANUAL

    if session.requirement_id:
        requirement = db.get(Requirement, session.requirement_id)
        data.requirement_title = requirement.title if requirement else None
    if session.knowledge_base_id:
        knowledge_base = db.get(KnowledgeBase, session.knowledge_base_id)
        data.knowledge_base_name = (
            knowledge_base.name if knowledge_base else None
        )

    points = (
        db.execute(
            select(GeneratedTestPoint)
            .where(GeneratedTestPoint.session_id == session.id)
            .order_by(GeneratedTestPoint.order.asc())
        )
        .scalars()
        .all()
    )
    cases = (
        db.execute(
            select(GeneratedCase)
            .where(GeneratedCase.session_id == session.id)
            .order_by(GeneratedCase.order.asc())
        )
        .scalars()
        .all()
    )
    data.test_points = [
        TestPointItem(
            id=point.id,
            order=point.order,
            module=point.module,
            point=point.point,
            category=point.category,
            priority=point.priority,
            selected=point.selected,
            trace_source=point.trace_source,
        )
        for point in points
    ]
    data.cases = [
        GeneratedCaseItem(
            id=case.id,
            order=case.order,
            title=case.title,
            module=case.module,
            category=case.category,
            priority=case.priority,
            preconditions=case.preconditions,
            steps=list(case.steps or []),
            expected=case.expected,
            trace_source=case.trace_source,
            selected=case.selected,
            imported_case_id=case.imported_case_id,
        )
        for case in cases
    ]
    return data


def _append_message(
    session: TestDesignSession, role: str, content: str, kind: str = "text"
) -> None:
    messages = list(session.messages or [])
    messages.append({"role": role, "content": content, "kind": kind})
    session.messages = messages


def _replace_points(
    db: Session, session: TestDesignSession, drafts: list[TestPointDraft]
) -> list[GeneratedTestPoint]:
    """用新测试点替换旧测试点（重新拆解场景）."""
    db.execute(
        delete(GeneratedTestPoint).where(
            GeneratedTestPoint.session_id == session.id
        )
    )
    db.execute(
        delete(GeneratedCase).where(GeneratedCase.session_id == session.id)
    )
    db.flush()
    points: list[GeneratedTestPoint] = []
    for index, draft in enumerate(drafts):
        point = GeneratedTestPoint(
            session_id=session.id,
            order=index,
            module=draft.module,
            point=draft.point,
            category=draft.category,
            priority=draft.priority,
            trace_source=draft.trace_source,
            selected=True,
        )
        db.add(point)
        points.append(point)
    db.commit()
    return points


def _selected_point_drafts(db: Session, session: TestDesignSession) -> list[TestPointDraft]:
    points = (
        db.execute(
            select(GeneratedTestPoint)
            .where(
                GeneratedTestPoint.session_id == session.id,
                GeneratedTestPoint.selected.is_(True),
            )
            .order_by(GeneratedTestPoint.order.asc())
        )
        .scalars()
        .all()
    )
    return [
        TestPointDraft(
            module=point.module,
            point=point.point,
            category=point.category,
            priority=point.priority,
            trace_source=point.trace_source,
        )
        for point in points
    ]


def _replace_cases(
    db: Session, session: TestDesignSession, drafts: list[CaseDraft]
) -> list[GeneratedCase]:
    db.execute(
        delete(GeneratedCase).where(GeneratedCase.session_id == session.id)
    )
    db.flush()
    cases: list[GeneratedCase] = []
    for index, draft in enumerate(drafts):
        case = GeneratedCase(
            session_id=session.id,
            order=index,
            title=draft.title,
            module=draft.module,
            category=draft.category,
            priority=draft.priority,
            preconditions=draft.preconditions,
            steps=draft.steps,
            expected=draft.expected,
            trace_source=draft.trace_source,
            test_data=draft.test_data,
            request_method=draft.request_method,
            request_url=draft.request_url,
            request_headers=draft.request_headers,
            request_body=draft.request_body,
            assertions=draft.assertions,
            selected=True,
        )
        db.add(case)
        cases.append(case)
    db.commit()
    return cases


def _cases_payload(db: Session, session: TestDesignSession) -> list[dict[str, Any]]:
    cases = (
        db.execute(
            select(GeneratedCase)
            .where(GeneratedCase.session_id == session.id)
            .order_by(GeneratedCase.order.asc())
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": case.id,
            "title": case.title,
            "module": case.module,
            "category": case.category,
            "priority": case.priority,
            "preconditions": case.preconditions,
            "steps": list(case.steps or []),
            "expected": case.expected,
            "trace_source": case.trace_source,
            "test_data": list(case.test_data or []),
            "request_method": case.request_method,
            "request_url": case.request_url,
            "request_headers": dict(case.request_headers or {}),
            "request_body": case.request_body,
            "assertions": list(case.assertions or []),
            # 有 method + url 才算可被引擎直接执行
            "executable": bool(case.request_method and case.request_url),
        }
        for case in cases
    ]


# ===========================================================================
# 会话
# ===========================================================================
@router.get("/sessions", response_model=PageResponse[TestDesignSessionResponse])
def list_sessions(
    project_id: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """生成会话列表."""
    query = select(TestDesignSession)
    count_q = select(func.count()).select_from(TestDesignSession)
    if project_id:
        query = query.where(TestDesignSession.project_id == project_id)
        count_q = count_q.where(TestDesignSession.project_id == project_id)
    if status:
        query = query.where(TestDesignSession.status == status)
        count_q = count_q.where(TestDesignSession.status == status)

    total = db.execute(count_q).scalar_one()
    items = (
        db.execute(
            query.order_by(TestDesignSession.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[TestDesignSessionResponse](
        data=[_session_response(db, item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/sessions", response_model=DataResponse[TestDesignSessionResponse])
def create_session(
    payload: TestDesignSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建生成会话；引用的需求与知识库必须存在."""
    if payload.mode not in _VALID_MODES:
        raise ValidationError(f"不支持的生成模式: {payload.mode}")
    if payload.requirement_id and not db.get(Requirement, payload.requirement_id):
        raise NotFoundError("需求", payload.requirement_id)
    if payload.knowledge_base_id and not db.get(
        KnowledgeBase, payload.knowledge_base_id
    ):
        raise NotFoundError("知识库", payload.knowledge_base_id)

    title = payload.title
    if not title and payload.requirement_id:
        requirement = db.get(Requirement, payload.requirement_id)
        title = requirement.title if requirement else None

    session = TestDesignSession(
        title=title,
        project_id=payload.project_id,
        requirement_id=payload.requirement_id,
        knowledge_base_id=payload.knowledge_base_id,
        mode=payload.mode,
        output_mode=(
            payload.output_mode
            if payload.output_mode in VALID_OUTPUT_MODES
            else MODE_MANUAL
        ),
        status="clarifying",
        review_dimensions=_normalize_dimensions(payload.review_dimensions),
        prompt=payload.prompt,
        messages=[],
        created_by=current_user.id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return DataResponse[TestDesignSessionResponse](
        data=_session_response(db, session)
    )


@router.get(
    "/sessions/{session_id}", response_model=DataResponse[TestDesignSessionResponse]
)
def get_session(session_id: str, db: Session = Depends(get_db)):
    """会话详情：含测试点与用例草稿."""
    session = _get_session_or_404(db, session_id)
    return DataResponse[TestDesignSessionResponse](
        data=_session_response(db, session)
    )


@router.delete("/sessions/{session_id}", response_model=ResponseBase)
def delete_session(session_id: str, db: Session = Depends(get_db)):
    """删除会话（级联删除测试点与用例草稿）."""
    session = _get_session_or_404(db, session_id)
    db.delete(session)
    db.commit()
    return ResponseBase()


# ===========================================================================
# 对话与测试点
# ===========================================================================
@router.post(
    "/sessions/{session_id}/messages",
    response_model=DataResponse[TestDesignSessionResponse],
)
def send_message(
    session_id: str,
    payload: SessionMessageRequest,
    db: Session = Depends(get_db),
):
    """继续对话：分步生成时用于回答 AI 的追问，帮助明确测试范围."""
    session = _get_session_or_404(db, session_id)
    _append_message(session, "user", payload.message)
    _append_message(
        session,
        "assistant",
        "已记录补充信息，可继续生成或重新拆解测试点。",
    )
    if session.prompt:
        session.prompt = f"{session.prompt}\n{payload.message}"
    else:
        session.prompt = payload.message
    db.commit()
    db.refresh(session)
    return DataResponse[TestDesignSessionResponse](
        data=_session_response(db, session)
    )


@router.post(
    "/sessions/{session_id}/generate-points",
    response_model=DataResponse[TestDesignSessionResponse],
)
def generate_points(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # noqa: ARG001
):
    """生成待确认测试点；分步模式会先提出缺失信息的问题."""
    session = _get_session_or_404(db, session_id)

    requirement_text = _requirement_text(db, session.requirement_id)
    if not requirement_text and not session.prompt:
        raise ValidationError(
            "请先选择需求或填写要测范围的描述，再生成测试点"
        )

    analysis = _latest_analysis(db, session.requirement_id)
    function_items = list(analysis.function_items or []) if analysis else []
    ui_descriptions = list(analysis.ui_descriptions or []) if analysis else []
    clarifications = list(analysis.clarifications or []) if analysis else []

    knowledge_context = ""
    if session.knowledge_base_id:
        query = "\n".join(
            part
            for part in (session.prompt or "", requirement_text[:2000])
            if part
        )
        knowledge_context, refs = _knowledge_service.retrieve_for_prompt(
            db, session.knowledge_base_id, query
        )
        session.knowledge_refs = [
            {
                "chunk_id": ref["chunk_id"],
                "document_name": ref["document_name"],
                "score": ref["score"],
            }
            for ref in refs
        ]

    # 分步生成：先根据缺失信息向测试人员提问
    if session.mode == "stepwise":
        questions = build_questions(
            session.title or "需求",
            requirement_text,
            function_items,
            clarifications,
        )
        if questions:
            _append_message(
                session,
                "assistant",
                "需求尚不明确，请补充以下信息：\n"
                + "\n".join(f"- {question}" for question in questions),
                kind="questions",
            )

    descriptions = [
        str(item.get("description") or "")
        for item in ui_descriptions
        if isinstance(item, dict)
    ]
    # 需求附件里的页面原型图：交给多模态模型，让它看到真实界面
    prototype_images = extract_image_data_urls(requirement_text)
    drafts, engine = generate_test_points(
        title=session.title or (session.prompt or "测试范围"),
        requirement_text=strip_image_markers(requirement_text or (session.prompt or "")),
        function_items=function_items,
        descriptions=descriptions,
        knowledge_context=knowledge_context,
        prototype_images=prototype_images,
    )
    if prototype_images:
        _append_message(
            session,
            "assistant",
            f"已识别 {len(prototype_images)} 张页面原型图，本次生成已结合原型。",
            kind="prototype",
        )

    _replace_points(db, session, drafts)
    session.engine = engine
    session.status = "points_ready"
    _append_message(
        session,
        "assistant",
        f"已生成 {len(drafts)} 个待确认测试点，确认后将据此生成用例。",
        kind="points",
    )
    db.commit()
    db.refresh(session)
    return DataResponse[TestDesignSessionResponse](
        data=_session_response(db, session)
    )


@router.put(
    "/sessions/{session_id}/points",
    response_model=DataResponse[TestDesignSessionResponse],
)
def update_points(
    session_id: str,
    payload: TestPointBulkUpdateRequest,
    db: Session = Depends(get_db),
):
    """批量修改测试点（模块、描述、分类、优先级）或调整勾选."""
    session = _get_session_or_404(db, session_id)
    points = {
        point.id: point
        for point in db.execute(
            select(GeneratedTestPoint).where(
                GeneratedTestPoint.session_id == session.id
            )
        )
        .scalars()
        .all()
    }
    for change in payload.points:
        point = points.get(change.id)
        if not point:
            continue
        for field in ("module", "point", "category", "priority", "selected"):
            value = getattr(change, field)
            if value is not None:
                setattr(point, field, value)
    db.commit()
    db.refresh(session)
    return DataResponse[TestDesignSessionResponse](
        data=_session_response(db, session)
    )


# ===========================================================================
# 用例生成
# ===========================================================================
@router.post(
    "/sessions/{session_id}/generate-cases",
    response_model=DataResponse[dict],
)
def generate_cases_endpoint(
    session_id: str,
    payload: GenerateCasesRequest | None = None,
    db: Session = Depends(get_db),
):
    """基于已确认测试点生成用例草稿（含前置条件、步骤与预期结果）."""
    session = _get_session_or_404(db, session_id)
    payload = payload or GenerateCasesRequest()

    all_points = (
        db.execute(
            select(GeneratedTestPoint)
            .where(GeneratedTestPoint.session_id == session.id)
            .order_by(GeneratedTestPoint.order.asc())
        )
        .scalars()
        .all()
    )
    if not all_points:
        raise ValidationError("请先生成并确认测试点")

    if payload.point_ids:
        wanted = set(payload.point_ids)
        chosen = [point for point in all_points if point.id in wanted]
    else:
        chosen = [point for point in all_points if point.selected]
    if not chosen:
        raise ValidationError("请至少勾选一个测试点")

    drafts = [
        TestPointDraft(
            module=point.module,
            point=point.point,
            category=point.category,
            priority=point.priority,
            trace_source=point.trace_source,
        )
        for point in chosen
    ]

    requirement_text = _requirement_text(db, session.requirement_id)
    knowledge_context = ""
    if session.knowledge_base_id:
        knowledge_context, _ = _knowledge_service.retrieve_for_prompt(
            db,
            session.knowledge_base_id,
            session.prompt or requirement_text[:2000],
        )

    # 产出形态：本次请求可临时指定，否则沿用会话设置
    output_mode = payload.output_mode
    if output_mode not in VALID_OUTPUT_MODES:
        output_mode = session.output_mode or MODE_MANUAL
    else:
        session.output_mode = output_mode

    case_drafts, engine = generate_cases(
        points=drafts,
        requirement_title=session.title or "需求",
        requirement_text=strip_image_markers(requirement_text),
        knowledge_context=knowledge_context,
        output_mode=output_mode,
        prototype_images=extract_image_data_urls(requirement_text),
    )

    point_by_title = {point.point: point.id for point in chosen}
    created = _replace_cases(db, session, case_drafts)
    # 回填测试点关联，便于追溯
    for case in created:
        drafts_title = case.title
        point_id = point_by_title.get(drafts_title)
        if point_id:
            case.test_point_id = point_id
    session.engine = engine
    session.status = "cases_ready"
    _append_message(
        session,
        "assistant",
        f"已根据 {len(chosen)} 个测试点生成 {len(created)} 条用例草稿",
        kind="cases",
    )
    db.commit()
    db.refresh(session)
    return DataResponse(
        data={
            "engine": engine,
            "case_count": len(created),
            "session": _session_response(db, session).model_dump(mode="json"),
        }
    )


@router.post(
    "/sessions/{session_id}/review", response_model=DataResponse[ReviewResponse]
)
def review_session(
    session_id: str,
    payload: ReviewRequest | None = None,
    db: Session = Depends(get_db),
):
    """按勾选的评审维度（含权重）对用例草稿做多维检查."""
    session = _get_session_or_404(db, session_id)
    dimensions = _normalize_dimensions(
        (payload.dimensions if payload else None) or session.review_dimensions
    )
    if payload and payload.dimensions:
        session.review_dimensions = dimensions
        db.commit()
    result = review_cases(_cases_payload(db, session), dimensions)
    return DataResponse[ReviewResponse](data=ReviewResponse(**result))


@router.post(
    "/sessions/{session_id}/import-cases",
    response_model=DataResponse[ImportCasesResponse],
)
def import_cases(
    session_id: str,
    payload: ImportCasesRequest | None = None,
    db: Session = Depends(get_db),
):
    """把选中的用例草稿写入功能测试用例库（FunctionalTestCase）.

    注意：不写入 API 自动化用例表（test_cases）。AI 生成的是功能测试用例，
    含前置条件/步骤/预期结果，与绑定 method/url/断言的 API 用例语义不同。
    """
    session = _get_session_or_404(db, session_id)
    payload = payload or ImportCasesRequest()

    query = select(GeneratedCase).where(GeneratedCase.session_id == session.id)
    if payload.case_ids:
        query = query.where(GeneratedCase.id.in_(payload.case_ids))
    else:
        query = query.where(GeneratedCase.selected.is_(True))
    cases = db.execute(query.order_by(GeneratedCase.order.asc())).scalars().all()
    if not cases:
        raise ValidationError("没有可写入的用例，请先生成或勾选用例")

    project_id = payload.project_id or session.project_id
    created_ids: list[str] = []
    api_case_ids: list[str] = []
    for case in cases:
        functional_case = FunctionalTestCase(
            title=case.title,
            module=case.module,
            category=case.category,
            priority=case.priority,
            preconditions=case.preconditions,
            steps=list(case.steps or []),
            expected=case.expected,
            trace_source=case.trace_source,
            # 测试数据与可执行请求一并落库，便于人工按数据执行
            test_data=list(case.test_data or []),
            request_method=case.request_method,
            request_url=case.request_url,
            request_headers=dict(case.request_headers or {}),
            request_body=case.request_body,
            assertions=list(case.assertions or []),
            status="active",
            source="ai",
            requirement_id=session.requirement_id,
            design_session_id=session.id,
            project_id=project_id,
        )
        db.add(functional_case)
        db.flush()
        case.imported_case_id = functional_case.id
        created_ids.append(functional_case.id)

        # 接口形态且具备 method+url 的用例，同时写入接口用例库，
        # 这样「可执行」才算兑现：导入后能在用例管理/接口列表里直接跑。
        if case.request_method and case.request_url:
            api_case = ApiCaseRecord(
                title=case.title[:256],
                method=str(case.request_method).upper()[:16],
                url=str(case.request_url)[:2048],
                headers=dict(case.request_headers or {}),
                params={},
                body=case.request_body,
                assertions=list(case.assertions or []),
                case_type=_API_CASE_TYPE_BY_CATEGORY.get(case.category, "normal"),
                priority=case.priority if case.priority in {"P0", "P1", "P2", "P3"} else "P1",
                status="active",
                source="ai",
                description=case.expected,
                interface_name=(case.title or "")[:256] or None,
                group_path=(case.module or "")[:256] or None,
                project_id=project_id,
            )
            db.add(api_case)
            db.flush()
            api_case_ids.append(api_case.id)

    # 回写需求的用例关联，保持需求覆盖率统计准确
    if session.requirement_id:
        requirement = db.get(Requirement, session.requirement_id)
        if requirement:
            existing = list(requirement.case_ids or [])
            requirement.case_ids = existing + [
                case_id for case_id in created_ids if case_id not in existing
            ]
            if requirement.status == "draft":
                requirement.status = "active"

    session.case_ids = list(dict.fromkeys([*(session.case_ids or []), *created_ids]))
    session.status = "imported"
    message = f"已写入功能测试用例库 {len(created_ids)} 条用例"
    if api_case_ids:
        message += f"，其中 {len(api_case_ids)} 条可执行用例已同时写入接口用例库"
    _append_message(session, "assistant", message, kind="import")
    db.commit()
    return DataResponse[ImportCasesResponse](
        data=ImportCasesResponse(
            created_count=len(created_ids),
            test_case_ids=created_ids,
            api_case_ids=api_case_ids,
        )
    )
