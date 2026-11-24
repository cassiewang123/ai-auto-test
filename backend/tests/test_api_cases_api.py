"""接口用例库（用例管理）API 测试."""

from __future__ import annotations

from io import BytesIO

from openpyxl import load_workbook

from app.models.api_case_record import ApiCaseRecord

BASE = "/api/v1/api-cases"


def _case_payload(**overrides):
    payload = {
        "title": "参数 tableName 缺失时返回校验错误",
        "method": "GET",
        "url": "/api/v1/codeTable/reset",
        "headers": {"Accept": "application/json"},
        "params": {"tableName": "COMPLEX"},
        "body": None,
        "assertions": [{"type": "status_code", "expected": "400"}],
        "case_type": "exception",
        "priority": "P1",
        "description": "自动生成",
        "interface_name": "重置指定码表缓存",
        "group_path": "swgd-param/1. 码表",
    }
    payload.update(overrides)
    return payload


def _bulk_import(client, cases=None, **overrides):
    payload = {
        "cases": cases or [_case_payload()],
        "interface_name": "重置指定码表缓存",
        "group_path": "swgd-param/1. 码表",
    }
    payload.update(overrides)
    response = client.post(f"{BASE}/bulk-import", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_bulk_import_creates_records(client, db_session):
    result = _bulk_import(
        client,
        cases=[
            _case_payload(title="正常请求", case_type="normal", priority="P0"),
            _case_payload(title="边界值校验", case_type="boundary"),
        ],
    )
    assert result["created_count"] == 2

    stored = db_session.query(ApiCaseRecord).all()
    assert len(stored) == 2
    assert {item.title for item in stored} == {"正常请求", "边界值校验"}
    assert all(item.source == "ai" for item in stored)
    assert all(item.interface_name == "重置指定码表缓存" for item in stored)


def test_bulk_import_skips_invalid_cases(client):
    result = _bulk_import(
        client,
        cases=[
            _case_payload(title="有效用例"),
            {"title": "", "url": "/x"},
            {"title": "缺少 URL"},
        ],
    )
    # 只有标题和 URL 齐全的用例会被导入
    assert result["created_count"] == 1


def test_bulk_import_rejects_empty(client):
    response = client.post(f"{BASE}/bulk-import", json={"cases": []})
    assert response.status_code == 422


def test_list_filters_by_case_type_and_method(client):
    _bulk_import(
        client,
        cases=[
            _case_payload(title="异常用例", case_type="exception"),
            _case_payload(title="正常用例", case_type="normal"),
            _case_payload(title="POST用例", method="POST", case_type="normal"),
        ],
    )

    listed = client.get(BASE, params={"case_type": "normal"}).json()
    assert listed["total"] == 2

    post_only = client.get(BASE, params={"method": "POST"}).json()
    assert post_only["total"] == 1
    assert post_only["data"][0]["title"] == "POST用例"


def test_stats_reflect_records(client):
    _bulk_import(
        client,
        cases=[
            _case_payload(title="a", case_type="normal", priority="P0"),
            _case_payload(title="b", case_type="exception"),
            _case_payload(title="c", case_type="boundary"),
        ],
    )
    stats = client.get(f"{BASE}/stats").json()["data"]
    assert stats["total"] == 3
    assert stats["normal"] == 1
    assert stats["exception"] == 1
    assert stats["boundary"] == 1
    assert stats["p0"] == 1


def test_create_update_delete_record(client, db_session):
    payload = _case_payload(title="手工用例", case_type="normal")
    created = client.post(BASE, json=payload)
    assert created.status_code == 200, created.text
    item = created.json()["data"]
    assert item["source"] == "manual"

    updated = client.put(
        f"{BASE}/{item['id']}", json={"title": "改名后", "priority": "P2"}
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["title"] == "改名后"

    deleted = client.delete(f"{BASE}/{item['id']}")
    assert deleted.status_code == 200
    assert db_session.get(ApiCaseRecord, item["id"]) is None


def test_reject_invalid_case_type(client):
    payload = _case_payload()
    payload["case_type"] = "unknown"
    response = client.post(BASE, json=payload)
    assert response.status_code == 422


def test_export_returns_xlsx(client):
    _bulk_import(
        client,
        cases=[
            _case_payload(title="导出用例A", case_type="normal"),
            _case_payload(title="导出用例B", case_type="exception"),
        ],
    )
    response = client.get(f"{BASE}/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in response.headers["content-disposition"]

    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook["接口用例"]
    headers = [cell.value for cell in sheet[1]]
    assert headers[:6] == ["序号", "用例标题", "场景", "方法", "URL", "优先级"]
    assert "请求体" in headers
    assert "断言" in headers
    assert sheet.max_row == 3


def test_export_respects_filters(client):
    _bulk_import(
        client,
        cases=[
            _case_payload(title="导出异常", case_type="exception"),
            _case_payload(title="导出正常", case_type="normal"),
        ],
    )
    response = client.get(f"{BASE}/export", params={"case_type": "normal"})
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook["接口用例"]
    titles = [sheet.cell(row=r, column=2).value for r in range(2, sheet.max_row + 1)]
    assert titles == ["导出正常"]


def test_export_route_not_shadowed_by_detail_route(client):
    """导出路由不能被 /{case_id} 通配路由吃掉."""
    created = client.post(BASE, json=_case_payload(title="详情路由")).json()["data"]
    detail = client.get(f"{BASE}/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["title"] == "详情路由"
