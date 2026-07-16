"""Project CRUD and project membership APIs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundError
from app.database import get_db
from app.models import Project, ProjectMember, TestCase, User
from app.schemas.common import DataResponse, PageResponse
from app.schemas.project import (
    ProjectCreate,
    ProjectMemberCreate,
    ProjectMemberResponse,
    ProjectMemberUpdate,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.auth_service import get_current_user
from app.services.project_access import ensure_project_role

router = APIRouter()


def _get_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError("项目", project_id)
    return project


def _member_query(user: User):
    query = select(Project)
    if not user.is_superuser:
        query = (
            query.join(
                ProjectMember,
                ProjectMember.project_id == Project.id,
            )
            .where(ProjectMember.user_id == user.id)
        )
    return query


def _ensure_owner_remains(
    db: Session,
    project_id: str,
    member: ProjectMember,
    next_role: str | None,
) -> None:
    if member.role != "owner" or next_role == "owner":
        return
    owner_count = db.execute(
        select(func.count())
        .select_from(ProjectMember)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.role == "owner",
        )
    ).scalar_one()
    if owner_count <= 1:
        raise AppException("项目必须至少保留一名 owner", status_code=409)


@router.get("", response_model=PageResponse[ProjectResponse])
def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List only projects visible to the current user."""
    query = _member_query(current_user)
    total = db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar_one()
    items = (
        db.execute(
            query.order_by(Project.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[ProjectResponse](
        data=items, total=total, page=page, page_size=page_size
    )


@router.get("/all", response_model=DataResponse[list[ProjectResponse]])
def list_all_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = db.execute(
        _member_query(current_user).order_by(Project.name)
    ).scalars().all()
    return DataResponse(data=items)


@router.post("", response_model=DataResponse[ProjectResponse])
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = Project(**payload.model_dump())
    db.add(project)
    db.flush()
    db.add(
        ProjectMember(
            project_id=project.id,
            user_id=current_user.id,
            role="owner",
            created_by=current_user.id,
        )
    )
    db.commit()
    db.refresh(project)
    return DataResponse[ProjectResponse](
        data=ProjectResponse.model_validate(project)
    )


@router.get("/{project_id}", response_model=DataResponse[ProjectResponse])
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_or_404(db, project_id)
    ensure_project_role(db, current_user, project_id)
    return DataResponse[ProjectResponse](
        data=ProjectResponse.model_validate(project)
    )


@router.put("/{project_id}", response_model=DataResponse[ProjectResponse])
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_or_404(db, project_id)
    ensure_project_role(db, current_user, project_id, "admin")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return DataResponse[ProjectResponse](
        data=ProjectResponse.model_validate(project)
    )


@router.delete("/{project_id}", response_model=DataResponse[ProjectResponse])
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_or_404(db, project_id)
    ensure_project_role(db, current_user, project_id, "owner")
    data = ProjectResponse.model_validate(project)
    db.delete(project)
    db.commit()
    return DataResponse[ProjectResponse](data=data)


@router.get("/{project_id}/stats", response_model=DataResponse[dict])
def project_stats(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_or_404(db, project_id)
    ensure_project_role(db, current_user, project_id)
    cases = db.execute(
        select(TestCase).where(TestCase.project_id == project_id)
    ).scalars().all()
    method_dist: dict[str, int] = {}
    for case in cases:
        method_dist[case.method] = method_dist.get(case.method, 0) + 1
    return DataResponse(
        data={"total": len(cases), "method_distribution": method_dist}
    )


@router.get(
    "/{project_id}/members",
    response_model=DataResponse[list[ProjectMemberResponse]],
)
def list_project_members(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_or_404(db, project_id)
    ensure_project_role(db, current_user, project_id)
    members = db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at)
    ).scalars().all()
    return DataResponse(data=members)


@router.post(
    "/{project_id}/members",
    response_model=DataResponse[ProjectMemberResponse],
)
def add_project_member(
    project_id: str,
    payload: ProjectMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_or_404(db, project_id)
    ensure_project_role(db, current_user, project_id, "admin")
    if not db.get(User, payload.user_id):
        raise NotFoundError("用户", payload.user_id)
    existing = db.get(ProjectMember, (project_id, payload.user_id))
    if existing:
        raise AppException("用户已经是项目成员", status_code=409)
    member = ProjectMember(
        project_id=project_id,
        user_id=payload.user_id,
        role=payload.role,
        created_by=current_user.id,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return DataResponse(data=member)


@router.put(
    "/{project_id}/members/{user_id}",
    response_model=DataResponse[ProjectMemberResponse],
)
def update_project_member(
    project_id: str,
    user_id: str,
    payload: ProjectMemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_or_404(db, project_id)
    ensure_project_role(db, current_user, project_id, "admin")
    member = db.get(ProjectMember, (project_id, user_id))
    if not member:
        raise NotFoundError("项目成员", user_id)
    _ensure_owner_remains(db, project_id, member, payload.role)
    member.role = payload.role
    db.commit()
    db.refresh(member)
    return DataResponse(data=member)


@router.delete(
    "/{project_id}/members/{user_id}",
    response_model=DataResponse[ProjectMemberResponse],
)
def remove_project_member(
    project_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_or_404(db, project_id)
    ensure_project_role(db, current_user, project_id, "admin")
    member = db.get(ProjectMember, (project_id, user_id))
    if not member:
        raise NotFoundError("项目成员", user_id)
    _ensure_owner_remains(db, project_id, member, None)
    data = ProjectMemberResponse.model_validate(member)
    db.delete(member)
    db.commit()
    return DataResponse(data=data)
