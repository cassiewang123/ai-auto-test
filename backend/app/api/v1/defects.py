"""缺陷集成 API：从测试失败结果创建缺陷、列表、详情、状态更新与外部同步."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.defect_integration import DefectTicket
from app.models.test_case import TestCase
from app.models.test_result import TestResult
from app.models.user import User
from app.schemas.common import DataResponse, PageResponse
from app.services.auth_service import get_current_user
from app.services.project_access import (
    ensure_project_assignment,
    ensure_project_role,
    ensure_resource_role,
    scope_project_resources,
)

router = APIRouter()

# 允许的外部缺陷系统
_EXTERNAL_SYSTEMS = {"jira", "zentao", "gitlab", "azure_devops"}
_VALID_STATUSES = {"open", "in_progress", "resolved", "closed"}
_VALID_SEVERITIES = {"critical", "high", "normal", "low"}


def _get_or_404(db: Session, defect_id: str) -> DefectTicket:
    ticket = db.get(DefectTicket, defect_id)
    if not ticket:
        raise NotFoundError("缺陷", defect_id)
    return ticket


def _serialize(ticket: DefectTicket) -> dict:
    return {
        "id": ticket.id,
        "external_id": ticket.external_id,
        "external_system": ticket.external_system,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status,
        "severity": ticket.severity,
        "project_id": ticket.project_id,
        "test_result_id": ticket.test_result_id,
        "created_by": ticket.created_by,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
    }


class DefectCreate(BaseModel):
    """创建缺陷请求.

    可直接提供标题/描述，或仅提供 test_result_id 由系统从失败结果自动生成。
    """

    title: str | None = Field(default=None, max_length=500, description="缺陷标题")
    description: str | None = Field(default=None, description="缺陷描述")
    test_result_id: str | None = Field(default=None, description="关联的测试结果 ID")
    external_system: str | None = Field(default=None, description="外部系统：jira/zentao/gitlab/azure_devops")
    external_id: str | None = Field(default=None, description="外部系统缺陷 ID")
    status: str = Field(default="open", description="状态")
    severity: str = Field(default="normal", description="严重程度")
    project_id: str | None = Field(default=None, description="项目 ID")


class DefectUpdate(BaseModel):
    """更新缺陷请求."""

    title: str | None = None
    description: str | None = None
    status: str | None = None
    severity: str | None = None
    external_id: str | None = None
    external_system: str | None = None
    project_id: str | None = None


class DefectSyncResult(BaseModel):
    """同步结果."""

    synced: bool
    message: str


@router.get("", response_model=PageResponse[dict])
def list_defects(
    status: str | None = Query(None, description="按状态筛选"),
    severity: str | None = Query(None, description="按严重程度筛选"),
    project_id: str | None = Query(None, description="按项目筛选"),
    external_system: str | None = Query(None, description="按外部系统筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """缺陷列表分页."""
    stmt = select(DefectTicket)
    count_stmt = select(func.count()).select_from(DefectTicket)
    if project_id:
        ensure_project_role(db, current_user, project_id, "viewer")
    stmt = scope_project_resources(stmt, DefectTicket, current_user)
    count_stmt = scope_project_resources(
        count_stmt, DefectTicket, current_user
    )

    if status:
        stmt = stmt.where(DefectTicket.status == status)
        count_stmt = count_stmt.where(DefectTicket.status == status)
    if severity:
        stmt = stmt.where(DefectTicket.severity == severity)
        count_stmt = count_stmt.where(DefectTicket.severity == severity)
    if project_id:
        stmt = stmt.where(DefectTicket.project_id == project_id)
        count_stmt = count_stmt.where(DefectTicket.project_id == project_id)
    if external_system:
        stmt = stmt.where(DefectTicket.external_system == external_system)
        count_stmt = count_stmt.where(DefectTicket.external_system == external_system)

    total = db.execute(count_stmt).scalar_one()
    items = (
        db.execute(
            stmt.order_by(desc(DefectTicket.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    data = [_serialize(i) for i in items]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.post("", response_model=DataResponse[dict])
def create_defect(
    payload: DefectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从测试失败结果或直接输入创建缺陷.

    - 若提供 test_result_id 且未提供 title，则自动从失败结果生成标题与描述。
    - 校验 status / severity / external_system 取值合法性。
    """
    title = payload.title
    description = payload.description
    project_id = payload.project_id
    test_result_id = payload.test_result_id

    if test_result_id:
        result = db.get(TestResult, test_result_id)
        if not result:
            raise NotFoundError("TestResult", test_result_id)
        case = db.get(TestCase, result.test_case_id) if result.test_case_id else None
        if case:
            ensure_resource_role(
                db, current_user, case, "viewer", owner_field=None
            )
        if not title:
            case_name = case.title if case else result.test_case_id or "未知用例"
            title = f"[测试失败] {case_name}"
        if not description:
            parts = [f"状态: {result.status}"]
            if result.error_message:
                parts.append(f"错误: {result.error_message}")
            if result.error_traceback:
                parts.append(f"堆栈:\n{result.error_traceback}")
            description = "\n".join(parts)
        if not project_id and case and getattr(case, "project_id", None):
            project_id = case.project_id
    elif not title:
        # 既无 test_result_id 又无 title，无法创建
        from app.core.exceptions import ValidationError

        raise ValidationError("title 与 test_result_id 至少需提供一个")

    if payload.status and payload.status not in _VALID_STATUSES:
        from app.core.exceptions import ValidationError

        raise ValidationError(f"非法状态，可选: {','.join(sorted(_VALID_STATUSES))}")
    if payload.severity and payload.severity not in _VALID_SEVERITIES:
        from app.core.exceptions import ValidationError

        raise ValidationError(f"非法严重程度，可选: {','.join(sorted(_VALID_SEVERITIES))}")
    if payload.external_system and payload.external_system not in _EXTERNAL_SYSTEMS:
        from app.core.exceptions import ValidationError

        raise ValidationError(
            f"非法外部系统，可选: {','.join(sorted(_EXTERNAL_SYSTEMS))}"
        )

    ensure_project_assignment(
        db,
        current_user,
        project_id,
        "developer",
        allow_unscoped_owner=True,
        unscoped_owner_id=current_user.id,
    )
    ticket = DefectTicket(
        title=title,
        description=description,
        external_id=payload.external_id,
        external_system=payload.external_system,
        status=payload.status,
        severity=payload.severity,
        project_id=project_id,
        test_result_id=test_result_id,
        created_by=current_user.id,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return DataResponse(data=_serialize(ticket))


@router.get("/{defect_id}", response_model=DataResponse[dict])
def get_defect(
    defect_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """缺陷详情."""
    ticket = _get_or_404(db, defect_id)
    ensure_resource_role(db, current_user, ticket, "viewer")
    return DataResponse(data=_serialize(ticket))


@router.put("/{defect_id}", response_model=DataResponse[dict])
def update_defect(
    defect_id: str,
    payload: DefectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新缺陷状态/字段."""
    ticket = _get_or_404(db, defect_id)
    ensure_resource_role(db, current_user, ticket, "developer")
    data = payload.model_dump(exclude_unset=True)
    if "project_id" in data and data["project_id"] != ticket.project_id:
        ensure_resource_role(db, current_user, ticket, "admin")
        ensure_project_assignment(
            db,
            current_user,
            data["project_id"],
            "admin",
            allow_unscoped_owner=True,
            unscoped_owner_id=ticket.created_by,
        )
    if "status" in data and data["status"] and data["status"] not in _VALID_STATUSES:
        from app.core.exceptions import ValidationError

        raise ValidationError(f"非法状态，可选: {','.join(sorted(_VALID_STATUSES))}")
    if (
        "severity" in data
        and data["severity"]
        and data["severity"] not in _VALID_SEVERITIES
    ):
        from app.core.exceptions import ValidationError

        raise ValidationError(
            f"非法严重程度，可选: {','.join(sorted(_VALID_SEVERITIES))}"
        )
    if (
        "external_system" in data
        and data["external_system"]
        and data["external_system"] not in _EXTERNAL_SYSTEMS
    ):
        from app.core.exceptions import ValidationError

        raise ValidationError(
            f"非法外部系统，可选: {','.join(sorted(_EXTERNAL_SYSTEMS))}"
        )
    for field, value in data.items():
        setattr(ticket, field, value)
    db.commit()
    db.refresh(ticket)
    return DataResponse(data=_serialize(ticket))


@router.post("/{defect_id}/sync", response_model=DataResponse[DefectSyncResult])
def sync_defect(
    defect_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """同步外部系统状态.

    当前为占位实现：若缺陷已配置 external_system 与 external_id，则标记为已同步；
    否则提示需先配置外部系统信息。真实集成在各 provider 适配器中实现。
    """
    ticket = _get_or_404(db, defect_id)
    ensure_resource_role(db, current_user, ticket, "admin")
    if ticket.external_system and ticket.external_id:
        return DataResponse(
            data=DefectSyncResult(
                synced=True,
                message=f"已与 {ticket.external_system} (ID: {ticket.external_id}) 同步",
            )
        )
    return DataResponse(
        data=DefectSyncResult(
            synced=False,
            message="尚未配置外部系统或外部 ID，无法同步",
        )
    )
