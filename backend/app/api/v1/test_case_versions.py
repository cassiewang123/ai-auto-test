"""用例版本管理 API（Phase 4）.

端点：
- POST /test-cases/{case_id}/submit-review   提交评审（draft → review）
- POST /test-cases/{case_id}/approve          审批通过（review → review，记录审批人）
- POST /test-cases/{case_id}/publish          发布（review → published，version +1）
- POST /test-cases/{case_id}/deprecate        废弃（任意状态 → deprecated）
- GET  /test-cases/{case_id}/versions         查看版本历史（沿 parent_case_id 链向上回溯）
- POST /test-cases/{case_id}/rollback         回滚到指定版本（基于指定版本复制新建一个 draft）

设计说明：
- 状态机：draft → review → published → deprecated（任意状态可转 deprecated）
- 发布时：当前用例状态置为 deprecated，并复制其内容创建新的 published 版本，
  新版本的 parent_case_id 指向旧版本，version = parent.version + 1。
- 回滚时：基于指定 target_version_id 复制内容创建一个 draft 版本，
  不直接覆盖现有版本，保证版本链可追溯。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.test_case import AssertionRule, TestCase
from app.schemas.common import DataResponse
from app.schemas.test_case import TestCaseResponse
from app.services.auth_service import get_current_user
from app.models.user import User

router = APIRouter()


# ---------------------------------------------------------------------------
# 状态机常量
# ---------------------------------------------------------------------------

STATUS_DRAFT = "draft"
STATUS_REVIEW = "review"
STATUS_PUBLISHED = "published"
STATUS_DEPRECATED = "deprecated"

_VALID_TRANSITIONS = {
    STATUS_DRAFT: {STATUS_REVIEW, STATUS_DEPRECATED},
    STATUS_REVIEW: {STATUS_PUBLISHED, STATUS_DEPRECATED},
    STATUS_PUBLISHED: {STATUS_DEPRECATED},
    STATUS_DEPRECATED: set(),
}


def _get_or_404(db: Session, case_id: str) -> TestCase:
    case = db.get(TestCase, case_id)
    if not case:
        raise NotFoundError("测试用例", case_id)
    return case


def _assert_transition(case: TestCase, target: str) -> None:
    current = case.case_status or STATUS_DRAFT
    if target not in _VALID_TRANSITIONS.get(current, set()):
        raise ValidationError(
            f"用例状态不允许从 '{current}' 转为 '{target}'",
            detail=f"current={current}, target={target}",
        )


# ---------------------------------------------------------------------------
# 序列化辅助
# ---------------------------------------------------------------------------


def _serialize_version_brief(case: TestCase) -> dict:
    """版本链中每个用例的简要信息。"""
    return {
        "id": case.id,
        "version": case.version,
        "case_status": case.case_status,
        "title": case.title,
        "parent_case_id": case.parent_case_id,
        "reviewer_id": case.reviewer_id,
        "approved_by": case.approved_by,
        "published_at": case.published_at.isoformat() if case.published_at else None,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
    }


# ---------------------------------------------------------------------------
# 复制用例（用于发布新版本 / 回滚）
# ---------------------------------------------------------------------------


# 复制时需要继承的字段（请求定义相关），版本管理字段单独处理
_COPY_FIELDS = (
    "title", "description", "group_path", "markers", "method", "url",
    "headers", "params", "body", "graphql_query", "files",
    "extract_rules", "project_id", "environment_id", "is_active", "sort_order",
    "retry_count", "retry_interval", "pre_script", "post_script",
)


def _copy_case_content(src: TestCase, **overrides) -> TestCase:
    """复制 src 的内容字段到新 TestCase 实例（不含 id / 版本字段）。"""
    data = {field: getattr(src, field) for field in _COPY_FIELDS}
    data.update(overrides)
    return TestCase(**data)


def _copy_assertions(db: Session, src: TestCase, new_case_id: str) -> None:
    """复制 src 的断言规则到 new_case_id。"""
    for a in src.assertions:
        db.add(
            AssertionRule(
                test_case_id=new_case_id,
                assertion_type=a.assertion_type,
                expression=a.expression,
                operator=a.operator,
                expected=a.expected,
                priority=a.priority,
                order=a.order,
            )
        )


# ---------------------------------------------------------------------------
# 状态流转端点
# ---------------------------------------------------------------------------


@router.post("/{case_id}/submit-review", response_model=DataResponse[TestCaseResponse])
def submit_review(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """提交评审：draft → review，记录 reviewer_id。"""
    case = _get_or_404(db, case_id)
    _assert_transition(case, STATUS_REVIEW)
    case.case_status = STATUS_REVIEW
    case.reviewer_id = user.id
    db.commit()
    db.refresh(case)
    return DataResponse[TestCaseResponse](data=case)


@router.post("/{case_id}/approve", response_model=DataResponse[TestCaseResponse])
def approve_case(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """审批通过：记录 approved_by，状态保持 review（等待 publish 才正式生效）。

    设计上 approve 不改变状态，只是打上审批人标记；publish 时校验必须有 approved_by。
    """
    case = _get_or_404(db, case_id)
    if (case.case_status or STATUS_DRAFT) != STATUS_REVIEW:
        raise ValidationError(
            f"仅处于 '{STATUS_REVIEW}' 状态的用例可审批，当前状态为 '{case.case_status}'"
        )
    case.approved_by = user.id
    db.commit()
    db.refresh(case)
    return DataResponse[TestCaseResponse](data=case)


@router.post("/{case_id}/publish", response_model=DataResponse[TestCaseResponse])
def publish_case(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """发布用例：review → published。

    流程：
    1. 校验当前状态为 review 且已审批（approved_by 非空）
    2. 将当前用例状态置为 published，设置 published_at
    3. version 保持不变（同一条记录的版本号仅在作为父版本时被引用）
    """
    case = _get_or_404(db, case_id)
    _assert_transition(case, STATUS_PUBLISHED)
    if not case.approved_by:
        raise ValidationError("用例尚未审批通过，无法发布")
    case.case_status = STATUS_PUBLISHED
    case.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(case)
    return DataResponse[TestCaseResponse](data=case)


@router.post("/{case_id}/deprecate", response_model=DataResponse[TestCaseResponse])
def deprecate_case(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """废弃用例：任意状态 → deprecated。"""
    case = _get_or_404(db, case_id)
    _assert_transition(case, STATUS_DEPRECATED)
    case.case_status = STATUS_DEPRECATED
    db.commit()
    db.refresh(case)
    return DataResponse[TestCaseResponse](data=case)


# ---------------------------------------------------------------------------
# 版本历史 & 回滚
# ---------------------------------------------------------------------------


@router.get("/{case_id}/versions", response_model=DataResponse[list[dict]])
def list_versions(
    case_id: str,
    db: Session = Depends(get_db),
):
    """查看用例版本历史。

    沿 parent_case_id 链向上回溯到最早的祖先，再向下查出所有后代（包括自身），
    按版本号升序返回。当前用例可能位于版本链中间任一节点。
    """
    case = _get_or_404(db, case_id)

    # 1. 找到祖先：沿 parent_case_id 向上
    ancestor_ids: list[str] = []
    current: TestCase | None = case
    visited: set[str] = set()
    while current and current.id not in visited:
        visited.add(current.id)
        ancestor_ids.insert(0, current.id)
        if current.parent_case_id:
            current = db.get(TestCase, current.parent_case_id)
        else:
            current = None

    if not ancestor_ids:
        # 不应该发生，至少包含自身
        ancestor_ids = [case.id]

    root_id = ancestor_ids[0]

    # 2. 从 root 开始，递归向下查找所有 parent_case_id 指向链中节点的用例
    #    为避免递归 SQL，使用迭代广度优先
    chain_ids: list[str] = [root_id]
    pending: list[str] = [root_id]
    while pending:
        # 查找 parent_case_id 在 pending 中的所有用例
        stmt = select(TestCase.id).where(TestCase.parent_case_id.in_(pending))
        child_ids = list(db.execute(stmt).scalars().all())
        # 去重并追加
        new_ids = [cid for cid in child_ids if cid not in chain_ids]
        chain_ids.extend(new_ids)
        pending = new_ids

    # 3. 查询所有链上用例并按 version 排序
    stmt = select(TestCase).where(TestCase.id.in_(chain_ids)).order_by(TestCase.version.asc())
    cases = list(db.execute(stmt).scalars().all())
    data = [_serialize_version_brief(c) for c in cases]
    return DataResponse(data=data)


class RollbackRequest(BaseModel):
    """回滚请求：基于哪个版本创建新的 draft 副本。"""

    target_version_id: str = Field(
        ..., description="要回滚到的目标版本用例 ID"
    )


@router.post("/{case_id}/rollback", response_model=DataResponse[TestCaseResponse])
def rollback_case(
    case_id: str,
    payload: RollbackRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """回滚到指定版本。

    不直接覆盖现有用例，而是基于 target_version_id 的内容创建一个新的 draft 副本，
    parent_case_id 指向 target_version_id，version = target.version + 1，
    由人工确认后再走 submit-review → approve → publish 流程。
    """
    case = _get_or_404(db, case_id)
    target = db.get(TestCase, payload.target_version_id)
    if not target:
        raise NotFoundError("目标版本用例", payload.target_version_id)

    # 计算 new version：取 target.version + 1
    new_version = (target.version or 1) + 1

    new_case = _copy_case_content(
        target,
        title=f"{target.title} (回滚自 v{target.version})",
        version=new_version,
        case_status=STATUS_DRAFT,
        parent_case_id=target.id,
        reviewer_id=None,
        approved_by=None,
        published_at=None,
    )
    db.add(new_case)
    db.flush()
    _copy_assertions(db, target, new_case.id)
    db.commit()
    db.refresh(new_case)
    return DataResponse[TestCaseResponse](data=new_case)


__all__ = ["router"]
