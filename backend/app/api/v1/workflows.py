"""DAG 工作流 CRUD 与执行 API.

端点：
    GET    /workflows              — 列表
    POST   /workflows              — 创建
    GET    /workflows/{id}         — 详情
    PUT    /workflows/{id}         — 更新
    DELETE /workflows/{id}         — 删除
    POST   /workflows/{id}/publish — 发布
    POST   /workflows/{id}/run     — 执行工作流
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.user import User
from app.models.workflow import WorkflowDefinition, WorkflowRun
from app.schemas.common import DataResponse, PageResponse
from app.schemas.workflow import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionResponse,
    WorkflowDefinitionUpdate,
    WorkflowRunCreate,
    WorkflowRunResponse,
)
from app.services.auth_service import get_current_user
from app.services.project_access import (
    ensure_project_assignment,
    ensure_project_role,
    ensure_resource_role,
    scope_project_resources,
)

router = APIRouter()


def _parse_json(raw: str | None, default: Any) -> Any:
    """将 Text 中存储的 JSON 字符串解析为 Python 对象."""
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default


def _dump_json(value: Any) -> str:
    """将 Python 对象序列化为 JSON 字符串以存入 Text 字段."""
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def _to_definition_response(wf: WorkflowDefinition) -> WorkflowDefinitionResponse:
    """将 WorkflowDefinition ORM 对象转为响应（解析 Text 中的 JSON）."""
    return WorkflowDefinitionResponse(
        id=wf.id,
        name=wf.name,
        description=wf.description,
        project_id=wf.project_id,
        nodes=_parse_json(wf.nodes, None),
        edges=_parse_json(wf.edges, None),
        version=wf.version,
        status=wf.status,
        created_by=wf.created_by,
        created_at=wf.created_at,
        updated_at=wf.updated_at,
    )


def _to_run_response(run: WorkflowRun) -> WorkflowRunResponse:
    """将 WorkflowRun ORM 对象转为响应."""
    return WorkflowRunResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_version=run.workflow_version,
        status=run.status,
        context=_parse_json(run.context, None),
        node_results=_parse_json(run.node_results, None),
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_message=run.error_message,
        created_by=run.created_by,
        created_at=run.created_at,
    )


def _topological_sort(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """对 DAG 节点进行拓扑排序，返回有序节点列表.

    检测环依赖并抛出 ValidationError。
    """
    node_ids = [n.get("id") for n in nodes if n.get("id")]
    node_map = {n["id"]: n for n in nodes if n.get("id")}
    # 邻接表与入度
    adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
    in_degree: dict[str, int] = dict.fromkeys(node_ids, 0)
    for edge in edges:
        src = edge.get("source") or edge.get("from")
        tgt = edge.get("target") or edge.get("to")
        if src in adjacency and tgt in in_degree:
            adjacency[src].append(tgt)
            in_degree[tgt] += 1

    # Kahn 算法
    queue = [nid for nid in node_ids if in_degree[nid] == 0]
    ordered: list[str] = []
    while queue:
        current = queue.pop(0)
        ordered.append(current)
        for neighbor in adjacency[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(ordered) != len(node_ids):
        raise ValidationError("工作流存在环依赖，无法进行拓扑排序")

    return [node_map[nid] for nid in ordered if nid in node_map]


def _execute_workflow(
    wf: WorkflowDefinition, context: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], str | None]:
    """同步执行工作流 DAG，返回 (节点结果列表, 错误信息).

    简化实现：按拓扑顺序遍历节点，记录每个节点的执行状态。
    节点类型由 node.type 标识（如 test_case / http_request / delay），
    实际执行逻辑可后续扩展为异步任务调度。
    """
    nodes = _parse_json(wf.nodes, []) or []
    edges = _parse_json(wf.edges, []) or []
    if not nodes:
        return [], None

    ordered = _topological_sort(nodes, edges)
    ctx = dict(context or {})
    results: list[dict[str, Any]] = []
    for node in ordered:
        node_id = node.get("id")
        node_type = node.get("type", "unknown")
        # 简化：所有节点标记为 succeeded，实际应按类型分发执行
        results.append(
            {
                "node_id": node_id,
                "node_type": node_type,
                "status": "succeeded",
                "output": node.get("config", {}),
                "context": ctx,
            }
        )
    return results, None


@router.get("", response_model=PageResponse[WorkflowDefinitionResponse])
def list_workflows(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    name: str | None = Query(None, description="按名称模糊搜索"),
    project_id: str | None = Query(None, description="按项目筛选"),
    status: str | None = Query(None, description="按状态筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """工作流定义列表分页，支持按 name / project_id / status 筛选."""
    query = select(WorkflowDefinition)
    count_query = select(func.count()).select_from(WorkflowDefinition)
    if project_id:
        ensure_project_role(db, current_user, project_id, "viewer")
    query = scope_project_resources(query, WorkflowDefinition, current_user)
    count_query = scope_project_resources(
        count_query, WorkflowDefinition, current_user
    )
    if name:
        query = query.where(WorkflowDefinition.name.ilike(f"%{name}%"))
    if project_id:
        query = query.where(WorkflowDefinition.project_id == project_id)
    if status:
        query = query.where(WorkflowDefinition.status == status)

    if name:
        count_query = count_query.where(WorkflowDefinition.name.ilike(f"%{name}%"))
    if project_id:
        count_query = count_query.where(WorkflowDefinition.project_id == project_id)
    if status:
        count_query = count_query.where(WorkflowDefinition.status == status)
    total = db.execute(count_query).scalar_one()

    items = (
        db.execute(
            query.order_by(WorkflowDefinition.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PageResponse[WorkflowDefinitionResponse](
        data=[_to_definition_response(w) for w in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=DataResponse[WorkflowDefinitionResponse])
def create_workflow(
    payload: WorkflowDefinitionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建工作流定义."""
    ensure_project_assignment(
        db,
        current_user,
        payload.project_id,
        "developer",
        allow_unscoped_owner=True,
        unscoped_owner_id=current_user.id,
    )
    wf = WorkflowDefinition(
        name=payload.name,
        description=payload.description,
        project_id=payload.project_id,
        nodes=_dump_json(payload.nodes),
        edges=_dump_json(payload.edges),
        version=1,
        status="draft",
        created_by=current_user.id,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return DataResponse[WorkflowDefinitionResponse](data=_to_definition_response(wf))


@router.get("/{workflow_id}", response_model=DataResponse[WorkflowDefinitionResponse])
def get_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取工作流定义详情."""
    wf = db.get(WorkflowDefinition, workflow_id)
    if not wf:
        raise NotFoundError("工作流", workflow_id)
    ensure_resource_role(db, current_user, wf, "viewer")
    return DataResponse[WorkflowDefinitionResponse](data=_to_definition_response(wf))


@router.put("/{workflow_id}", response_model=DataResponse[WorkflowDefinitionResponse])
def update_workflow(
    workflow_id: str,
    payload: WorkflowDefinitionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新工作流定义（部分更新）."""
    wf = db.get(WorkflowDefinition, workflow_id)
    if not wf:
        raise NotFoundError("工作流", workflow_id)
    ensure_resource_role(db, current_user, wf, "developer")
    update_data = payload.model_dump(exclude_unset=True)
    if "status" in update_data:
        ensure_resource_role(db, current_user, wf, "admin")
    if "project_id" in update_data and update_data["project_id"] != wf.project_id:
        ensure_resource_role(db, current_user, wf, "admin")
        ensure_project_assignment(
            db,
            current_user,
            update_data["project_id"],
            "admin",
            allow_unscoped_owner=True,
            unscoped_owner_id=wf.created_by,
        )
    # JSON 字段需序列化为字符串
    if "nodes" in update_data:
        wf.nodes = _dump_json(update_data.pop("nodes"))
    if "edges" in update_data:
        wf.edges = _dump_json(update_data.pop("edges"))
    for field, value in update_data.items():
        setattr(wf, field, value)
    db.commit()
    db.refresh(wf)
    return DataResponse[WorkflowDefinitionResponse](data=_to_definition_response(wf))


@router.delete("/{workflow_id}", response_model=DataResponse[WorkflowDefinitionResponse])
def delete_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除工作流定义."""
    wf = db.get(WorkflowDefinition, workflow_id)
    if not wf:
        raise NotFoundError("工作流", workflow_id)
    ensure_resource_role(db, current_user, wf, "admin")
    resp = _to_definition_response(wf)
    db.delete(wf)
    db.commit()
    return DataResponse[WorkflowDefinitionResponse](data=resp)


@router.post("/{workflow_id}/publish", response_model=DataResponse[WorkflowDefinitionResponse])
def publish_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发布工作流：状态置为 published 并自增版本号.

    发布前会校验 DAG 是否存在环依赖。
    """
    wf = db.get(WorkflowDefinition, workflow_id)
    if not wf:
        raise NotFoundError("工作流", workflow_id)
    ensure_resource_role(db, current_user, wf, "admin")
    # 校验 DAG 拓扑（环检测）
    nodes = _parse_json(wf.nodes, []) or []
    edges = _parse_json(wf.edges, []) or []
    if nodes:
        _topological_sort(nodes, edges)
    wf.status = "published"
    wf.version = (wf.version or 1) + 1
    db.commit()
    db.refresh(wf)
    return DataResponse[WorkflowDefinitionResponse](data=_to_definition_response(wf))


@router.post("/{workflow_id}/run", response_model=DataResponse[WorkflowRunResponse])
def run_workflow(
    workflow_id: str,
    payload: WorkflowRunCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行工作流：创建运行记录并同步执行 DAG."""
    wf = db.get(WorkflowDefinition, workflow_id)
    if not wf:
        raise NotFoundError("工作流", workflow_id)
    ensure_resource_role(db, current_user, wf, "tester")
    if wf.status != "published":
        raise ValidationError(
            f"工作流当前状态为 '{wf.status}'，仅 published 状态可执行"
        )

    now = datetime.now(timezone.utc)
    run = WorkflowRun(
        workflow_id=wf.id,
        workflow_version=wf.version,
        status="running",
        context=_dump_json(payload.context or {}),
        started_at=now,
        created_by=current_user.id,
    )
    db.add(run)
    db.flush()

    try:
        node_results, err = _execute_workflow(wf, payload.context)
        run.node_results = _dump_json(node_results)
        run.status = "failed" if err else "succeeded"
        run.error_message = err
    except ValidationError:
        run.status = "failed"
        run.error_message = "工作流执行失败：拓扑排序错误"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        raise
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_message = str(exc)

    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return DataResponse[WorkflowRunResponse](data=_to_run_response(run))
