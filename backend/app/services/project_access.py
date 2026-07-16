"""Project-scoped authorization helpers."""
from __future__ import annotations

from typing import Any

from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError
from app.models.execution_job import ExecutionJob
from app.models.project_member import PROJECT_ROLES, ProjectMember
from app.models.user import User

_ROLE_RANK = {role: rank for rank, role in enumerate(PROJECT_ROLES)}


def _roles_at_or_above(minimum_role: str) -> tuple[str, ...]:
    if minimum_role not in _ROLE_RANK:
        raise ValueError(f"Unknown project role: {minimum_role}")
    minimum_rank = _ROLE_RANK[minimum_role]
    return tuple(
        role for role in PROJECT_ROLES if _ROLE_RANK[role] >= minimum_rank
    )


def project_ids_for_role(user_id: str, minimum_role: str = "viewer"):
    """Return a scalar subquery selecting projects available to a user."""
    roles = _roles_at_or_above(minimum_role)
    return select(ProjectMember.project_id).where(
        ProjectMember.user_id == user_id,
        ProjectMember.role.in_(roles),
    )


def get_project_membership(
    db: Session,
    user_id: str,
    project_id: str,
) -> ProjectMember | None:
    return db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    ).scalar_one_or_none()


def ensure_project_role(
    db: Session,
    user: User,
    project_id: str,
    minimum_role: str = "viewer",
) -> ProjectMember | None:
    """Require project membership at or above ``minimum_role``."""
    if user.is_superuser:
        return None
    required_rank = _ROLE_RANK.get(minimum_role)
    if required_rank is None:
        raise ValueError(f"Unknown project role: {minimum_role}")

    membership = get_project_membership(db, user.id, project_id)
    if not membership or _ROLE_RANK.get(membership.role, -1) < required_rank:
        raise ForbiddenError("Project resource access denied")
    return membership


def ensure_project_assignment(
    db: Session,
    user: User,
    project_id: str | None,
    minimum_role: str = "developer",
    *,
    allow_unscoped_owner: bool = False,
    unscoped_owner_id: str | None = None,
) -> None:
    """Authorize assigning a resource to a project or to its creator."""
    if user.is_superuser:
        return
    if project_id:
        ensure_project_role(db, user, project_id, minimum_role)
        return
    if allow_unscoped_owner and unscoped_owner_id == user.id:
        return
    raise ForbiddenError("A project is required for this resource")


def ensure_resource_role(
    db: Session,
    user: User,
    resource: Any,
    minimum_role: str = "viewer",
    *,
    owner_field: str | None = "created_by",
) -> None:
    """Authorize access to a project resource or an owned legacy resource."""
    if user.is_superuser:
        return

    project_id = getattr(resource, "project_id", None)
    if project_id:
        ensure_project_role(db, user, project_id, minimum_role)
        return

    owner_id = getattr(resource, owner_field, None) if owner_field else None
    if owner_id and owner_id == user.id:
        return
    raise ForbiddenError("Legacy resource access denied")


def scope_project_resources(
    statement: Any,
    model: Any,
    user: User,
    minimum_role: str = "viewer",
    *,
    owner_field: str | None = "created_by",
):
    """Limit a SELECT to project memberships and owned legacy resources."""
    if user.is_superuser:
        return statement

    project_column = getattr(model, "project_id", None)
    if project_column is None:
        return statement.where(false())

    conditions = [
        project_column.in_(project_ids_for_role(user.id, minimum_role)),
    ]
    owner_column = getattr(model, owner_field, None) if owner_field else None
    if owner_column is not None:
        conditions.append(
            (project_column.is_(None)) & (owner_column == user.id)
        )
    return statement.where(or_(*conditions))


def ensure_job_access(
    db: Session,
    user: User,
    job: ExecutionJob,
    *,
    write: bool = False,
) -> None:
    """Require ownership or project membership for a task."""
    if user.is_superuser or job.created_by == user.id:
        return
    if not job.project_id:
        raise ForbiddenError("Task access denied")
    ensure_project_role(
        db,
        user,
        job.project_id,
        minimum_role="tester" if write else "viewer",
    )
