"""功能测试用例库 API 测试."""

from __future__ import annotations

from app.models.functional_test_case import (
    FunctionalCaseExecution,
    FunctionalTestCase,
)


def _create_case(client, **overrides):
    payload = {
        "title": "正常登录成功",
        "module": "登录与认证",
        "category": "功能",
        "priority": "P0",
        "preconditions": "已注册账号",
        "steps": ["打开登录页", "输入账号密码", "点击登录"],
        "expected": "登录成功并跳转首页",
        "trace_source": "用户名密码登录",
    }
    payload.update(overrides)
    response = client.post("/api/v1/functional-test-cases", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_create_and_get_functional_case(client):
    created = _create_case(client)
    assert created["title"] == "正常登录成功"
    assert created["source"] == "manual"
    assert created["status"] == "active"
    assert created["steps"] == ["打开登录页", "输入账号密码", "点击登录"]

    detail = client.get(f"/api/v1/functional-test-cases/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["module"] == "登录与认证"


def test_list_filters_by_module_and_priority(client):
    _create_case(client, title="用例A", module="登录与认证", priority="P0")
    _create_case(client, title="用例B", module="项目管理", priority="P2")

    listed = client.get(
        "/api/v1/functional-test-cases", params={"module": "登录与认证"}
    )
    assert listed.json()["total"] == 1
    assert listed.json()["data"][0]["title"] == "用例A"

    p0 = client.get("/api/v1/functional-test-cases", params={"priority": "P0"})
    assert p0.json()["total"] == 1


def test_update_and_delete_functional_case(client, db_session):
    created = _create_case(client)
    updated = client.put(
        f"/api/v1/functional-test-cases/{created['id']}",
        json={"title": "改名后的用例", "priority": "P2", "status": "draft"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["title"] == "改名后的用例"
    assert updated.json()["data"]["status"] == "draft"

    deleted = client.delete(f"/api/v1/functional-test-cases/{created['id']}")
    assert deleted.status_code == 200
    assert db_session.get(FunctionalTestCase, created["id"]) is None


def test_reject_invalid_priority_and_status(client):
    bad_priority = client.post(
        "/api/v1/functional-test-cases",
        json={"title": "非法优先级", "priority": "P9"},
    )
    assert bad_priority.status_code == 422

    bad_status = client.post(
        "/api/v1/functional-test-cases",
        json={"title": "非法状态", "status": "unknown"},
    )
    assert bad_status.status_code == 422


def test_reject_invalid_category(client):
    response = client.post(
        "/api/v1/functional-test-cases",
        json={"title": "非法分类", "category": "不存在"},
    )
    assert response.status_code == 422


def test_reject_unknown_requirement(client):
    response = client.post(
        "/api/v1/functional-test-cases",
        json={"title": "挂到不存在需求", "requirement_id": "not-exist"},
    )
    assert response.status_code == 404


def test_stats_reflects_cases(client):
    _create_case(client, title="用例1", priority="P0")
    _create_case(client, title="用例2", priority="P1", status="draft")
    _create_case(client, title="用例3", priority="P2", status="deprecated")

    stats = client.get("/api/v1/functional-test-cases/stats").json()["data"]
    assert stats["total"] == 3
    assert stats["p0"] == 1
    assert stats["draft"] == 1
    assert stats["deprecated"] == 1


def test_execution_records_and_last_result(client, db_session):
    created = _create_case(client)
    url = f"/api/v1/functional-test-cases/{created['id']}/executions"

    response = client.post(
        url,
        json={
            "result": "passed",
            "actual": "跳转到首页",
            "remark": "第一轮回归",
            "run_label": "round-1",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["result"] == "passed"

    client.post(url, json={"result": "failed", "actual": "提示密码错误"})

    history = client.get(url).json()["data"]
    assert len(history) == 2

    detail = client.get(f"/api/v1/functional-test-cases/{created['id']}").json()["data"]
    # 最近一次执行结果回填到用例上
    assert detail["last_result"] == "failed"
    assert detail["last_executed_at"] is not None


def test_reject_invalid_execution_result(client):
    created = _create_case(client)
    response = client.post(
        f"/api/v1/functional-test-cases/{created['id']}/executions",
        json={"result": "unknown-result"},
    )
    assert response.status_code == 422


def test_delete_case_cascades_executions(client, db_session):
    created = _create_case(client)
    client.post(
        f"/api/v1/functional-test-cases/{created['id']}/executions",
        json={"result": "passed"},
    )
    client.delete(f"/api/v1/functional-test-cases/{created['id']}")
    assert (
        db_session.query(FunctionalCaseExecution)
        .filter_by(case_id=created["id"])
        .count()
        == 0
    )


def test_requirement_case_ids_follow_functional_cases(client, db_session):
    """功能用例关联需求后，需求的 case_ids 应同步，供覆盖率统计."""
    requirement = client.post(
        "/api/v1/requirements",
        json={"title": "登录需求", "description": "登录功能"},
    ).json()["data"]
    req_id = requirement["id"]

    case = _create_case(client, requirement_id=req_id)
    detail = client.get(f"/api/v1/requirements/{req_id}").json()["data"]
    assert case["id"] in detail["case_ids"]
    assert detail["coverage"] == 1

    # 删除功能用例后需求关联同步移除
    client.delete(f"/api/v1/functional-test-cases/{case['id']}")
    detail = client.get(f"/api/v1/requirements/{req_id}").json()["data"]
    assert case["id"] not in detail["case_ids"]
    assert detail["coverage"] == 0


# ---------------------------------------------------------------------------
# Excel 导出
# ---------------------------------------------------------------------------
def test_export_returns_xlsx_with_headers_and_rows(client):
    from io import BytesIO

    from openpyxl import load_workbook

    _create_case(client, title="登录成功用例", priority="P0")
    _create_case(client, title="登录失败用例", category="异常", priority="P1")

    response = client.get("/api/v1/functional-test-cases/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in response.headers["content-disposition"]

    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook["功能测试用例"]
    headers = [cell.value for cell in sheet[1]]
    assert headers[:5] == ["序号", "用例标题", "模块", "分类", "优先级"]
    assert "操作步骤" in headers
    assert "预期结果" in headers
    # 表头之外应有两条用例
    assert sheet.max_row == 3


def test_export_writes_steps_as_numbered_lines(client):
    from io import BytesIO

    from openpyxl import load_workbook

    _create_case(
        client,
        title="带步骤用例",
        steps=["第一步操作", "第二步操作"],
    )

    response = client.get("/api/v1/functional-test-cases/export")
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook["功能测试用例"]
    headers = [cell.value for cell in sheet[1]]
    steps_col = headers.index("操作步骤") + 1
    steps_text = sheet.cell(row=2, column=steps_col).value
    assert "1. 第一步操作" in steps_text
    assert "2. 第二步操作" in steps_text


def test_export_respects_filters(client):
    from io import BytesIO

    from openpyxl import load_workbook

    _create_case(client, title="P0用例", priority="P0")
    _create_case(client, title="P2用例", priority="P2")

    response = client.get(
        "/api/v1/functional-test-cases/export", params={"priority": "P0"}
    )
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook["功能测试用例"]
    titles = [sheet.cell(row=r, column=2).value for r in range(2, sheet.max_row + 1)]
    assert titles == ["P0用例"]


def test_export_does_not_conflict_with_case_detail_route(client):
    """导出路由不能被 /{case_id} 通配路由吃掉."""
    created = _create_case(client, title="详情路由仍可用")
    detail = client.get(f"/api/v1/functional-test-cases/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["title"] == "详情路由仍可用"


def test_export_includes_latest_execution_result(client):
    from io import BytesIO

    from openpyxl import load_workbook

    created = _create_case(client, title="已执行用例")
    client.post(
        f"/api/v1/functional-test-cases/{created['id']}/executions",
        json={"result": "failed"},
    )

    response = client.get("/api/v1/functional-test-cases/export")
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook["功能测试用例"]
    headers = [cell.value for cell in sheet[1]]
    result_col = headers.index("最近执行结果") + 1
    assert sheet.cell(row=2, column=result_col).value == "失败"


# ---------------------------------------------------------------------------
# 批量删除
# ---------------------------------------------------------------------------
def test_batch_delete_removes_cases_and_executions(client, db_session):
    """批量删除应清掉用例与其执行记录."""
    ids = []
    for i in range(3):
        item = client.post(
            "/api/v1/functional-test-cases",
            json={"title": f"批量删除-{i}", "steps": ["a"], "expected": "b"},
        ).json()["data"]
        ids.append(item["id"])
        client.post(
            f"/api/v1/functional-test-cases/{item['id']}/executions",
            json={"result": "passed"},
        )

    response = client.post(
        "/api/v1/functional-test-cases/batch-delete", json={"case_ids": ids}
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["deleted"] == 3
    assert data["missing"] == 0

    left = client.get("/api/v1/functional-test-cases").json()
    assert left["total"] == 0
    # 执行记录必须一并清理，不能留孤儿数据
    from app.models.functional_test_case import FunctionalCaseExecution

    assert db_session.query(FunctionalCaseExecution).count() == 0


def test_batch_delete_only_affects_given_ids(client):
    keep = client.post(
        "/api/v1/functional-test-cases",
        json={"title": "保留的用例", "steps": ["a"], "expected": "b"},
    ).json()["data"]
    drop = client.post(
        "/api/v1/functional-test-cases",
        json={"title": "要删的用例", "steps": ["a"], "expected": "b"},
    ).json()["data"]

    client.post(
        "/api/v1/functional-test-cases/batch-delete",
        json={"case_ids": [drop["id"]]},
    )

    listed = client.get("/api/v1/functional-test-cases").json()
    assert listed["total"] == 1
    assert listed["data"][0]["id"] == keep["id"]


def test_batch_delete_reports_missing_ids(client):
    item = client.post(
        "/api/v1/functional-test-cases",
        json={"title": "存在的用例", "steps": ["a"], "expected": "b"},
    ).json()["data"]
    response = client.post(
        "/api/v1/functional-test-cases/batch-delete",
        json={"case_ids": [item["id"], "not-exist-id"]},
    )
    data = response.json()["data"]
    assert data["deleted"] == 1
    assert data["missing"] == 1


def test_batch_delete_requires_ids(client):
    response = client.post(
        "/api/v1/functional-test-cases/batch-delete", json={"case_ids": []}
    )
    assert response.status_code == 422


def test_batch_delete_tolerates_all_unknown_ids(client):
    """全部 ID 都不存在时视为无操作，而不是 500."""
    response = client.post(
        "/api/v1/functional-test-cases/batch-delete",
        json={"case_ids": ["a", "b"]},
    )
    assert response.status_code == 200
    assert response.json()["data"]["deleted"] == 0


def test_batch_delete_route_not_shadowed_by_detail_route(client):
    """/batch-delete 不能被 /{case_id} 通配路由吃掉."""
    item = client.post(
        "/api/v1/functional-test-cases",
        json={"title": "路由验证", "steps": ["a"], "expected": "b"},
    ).json()["data"]
    client.post(
        "/api/v1/functional-test-cases/batch-delete",
        json={"case_ids": [item["id"]]},
    )
    assert client.get(f"/api/v1/functional-test-cases/{item['id']}").status_code == 404


# ---------------------------------------------------------------------------
# 按模块查找
# ---------------------------------------------------------------------------
def test_modules_endpoint_lists_modules_with_counts(client):
    for title, module in (
        ("甲", "多式联运"),
        ("乙", "多式联运"),
        ("丙", "多式联运/导入校验"),
        ("丁", "报关"),
    ):
        client.post(
            "/api/v1/functional-test-cases",
            json={"title": title, "module": module, "steps": ["a"], "expected": "b"},
        )

    modules = client.get("/api/v1/functional-test-cases/modules").json()["data"]
    by_path = {item["path"]: item for item in modules}

    # 父子路径都被补齐
    assert set(by_path) == {"多式联运", "多式联运/导入校验", "报关"}
    assert by_path["多式联运"]["direct_count"] == 2
    # 含子模块的累计数
    assert by_path["多式联运"]["total_count"] == 3
    assert by_path["多式联运/导入校验"]["parent_path"] == "多式联运"
    assert by_path["报关"]["parent_path"] is None


def test_modules_endpoint_excludes_empty_module(client):
    client.post(
        "/api/v1/functional-test-cases",
        json={"title": "无模块", "steps": ["a"], "expected": "b"},
    )
    modules = client.get("/api/v1/functional-test-cases/modules").json()["data"]
    assert modules == []


def test_list_filters_by_module_including_children(client):
    for title, module in (
        ("父模块用例", "多式联运"),
        ("子模块用例", "多式联运/导入校验"),
        ("其他模块", "报关"),
    ):
        client.post(
            "/api/v1/functional-test-cases",
            json={"title": title, "module": module, "steps": ["a"], "expected": "b"},
        )

    parent = client.get(
        "/api/v1/functional-test-cases", params={"module": "多式联运"}
    ).json()
    assert parent["total"] == 2
    assert {item["title"] for item in parent["data"]} == {"父模块用例", "子模块用例"}

    child = client.get(
        "/api/v1/functional-test-cases", params={"module": "多式联运/导入校验"}
    ).json()
    assert child["total"] == 1
    assert child["data"][0]["title"] == "子模块用例"


def test_module_filter_does_not_match_sibling_prefix(client):
    client.post(
        "/api/v1/functional-test-cases",
        json={"title": "同类前缀", "module": "多式联运二期", "steps": ["a"], "expected": "b"},
    )
    result = client.get(
        "/api/v1/functional-test-cases", params={"module": "多式联运"}
    ).json()
    assert result["total"] == 0


def test_export_respects_module_filter(client):
    for title, module in (
        ("导出A", "多式联运"),
        ("导出B", "报关"),
    ):
        client.post(
            "/api/v1/functional-test-cases",
            json={"title": title, "module": module, "steps": ["a"], "expected": "b"},
        )
    response = client.get(
        "/api/v1/functional-test-cases/export", params={"module": "多式联运"}
    )
    assert response.status_code == 200
    from io import BytesIO

    from openpyxl import load_workbook

    sheet = load_workbook(BytesIO(response.content)).active
    headers = [cell.value for cell in sheet[1]]
    # 导出第 1 列是序号，标题按表头名定位，避免列顺序变动导致误判
    title_col = headers.index("用例标题") + 1
    titles = [
        sheet.cell(row=r, column=title_col).value
        for r in range(2, sheet.max_row + 1)
    ]
    assert titles == ["导出A"]
