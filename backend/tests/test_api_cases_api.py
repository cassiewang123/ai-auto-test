"""接口用例库（用例管理）API 测试."""

from __future__ import annotations

from io import BytesIO

from openpyxl import load_workbook

from app.models.api_case_record import ApiCaseRecord

BASE = "/api/v1/api-cases"


def _column_values(sheet, header: str) -> list:
    """按表头名取出整列的值（跳过表头行）.

    导出会纵向合并相同数据，合并后的单元格只有首行有值；这里按 original
    单元格取值，因此合并块只贡献一个值。断言列顺序调整后不再依赖下标。
    """
    headers = [cell.value for cell in sheet[1]]
    index = headers.index(header) + 1
    return [
        sheet.cell(row=row, column=index).value
        for row in range(2, sheet.max_row + 1)
        if sheet.cell(row=row, column=index).value is not None
    ]


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


def test_bulk_import_drops_non_dict_entries(client, db_session):
    """前端选中索引失效时可能传入 null/字符串/数组，不应导致整批 422."""
    result = _bulk_import(
        client,
        cases=[
            _case_payload(title="有效用例"),
            None,  # JSON.stringify(undefined) 产生的 null
            "not-a-dict",
            ["not", "a", "dict"],
        ],
    )
    assert result["created_count"] == 1
    stored = db_session.query(ApiCaseRecord).all()
    assert [item.title for item in stored] == ["有效用例"]


def test_bulk_import_all_invalid_entries_rejected(client):
    """全部为非法项时仍应返回 422（没有可导入的用例）。"""
    response = client.post(
        f"{BASE}/bulk-import", json={"cases": [None, "bad", ["bad"]]}
    )
    assert response.status_code == 422


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
    # 分组与关联接口排在最前，便于按模块/接口阅读
    assert headers[:6] == ["分组", "关联接口", "序号", "用例标题", "场景", "方法"]
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
    titles = _column_values(sheet, "用例标题")
    assert titles == ["导出正常"]


def test_export_route_not_shadowed_by_detail_route(client):
    """导出路由不能被 /{case_id} 通配路由吃掉."""
    created = client.post(BASE, json=_case_payload(title="详情路由")).json()["data"]
    detail = client.get(f"{BASE}/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["title"] == "详情路由"


# ---------- 模块（分组）维度 ----------


def test_bulk_import_keeps_per_case_group_path(client, db_session):
    """按模块批量生成时，同批用例可以分属不同接口和模块."""
    result = _bulk_import(
        client,
        cases=[
            _case_payload(
                title="A 接口用例",
                interface_name="A 接口",
                group_path="磐石关务/回执",
            ),
            _case_payload(
                title="B 接口用例",
                interface_name="B 接口",
                group_path="磐石关务/报文",
            ),
        ],
        interface_name="批量生成",
        group_path="",
    )
    assert result["created_count"] == 2

    stored = {
        item.title: (item.interface_name, item.group_path)
        for item in db_session.query(ApiCaseRecord).all()
    }
    assert stored["A 接口用例"] == ("A 接口", "磐石关务/回执")
    assert stored["B 接口用例"] == ("B 接口", "磐石关务/报文")


def test_bulk_import_falls_back_to_request_group_path(client, db_session):
    """用例自身没带分组时才回落到请求级分组."""
    _bulk_import(
        client,
        cases=[_case_payload(title="回落用例", interface_name=None, group_path=None)],
        interface_name="重置指定码表缓存",
        group_path="swgd-param/1. 码表",
    )
    item = db_session.query(ApiCaseRecord).one()
    assert item.group_path == "swgd-param/1. 码表"
    assert item.interface_name == "重置指定码表缓存"


def test_list_filters_by_group_including_children(client):
    _bulk_import(
        client,
        cases=[
            _case_payload(title="父模块用例", group_path="磐石关务"),
            _case_payload(title="子模块用例", group_path="磐石关务/回执"),
            _case_payload(title="孙模块用例", group_path="磐石关务/回执/新增"),
            _case_payload(title="其他模块用例", group_path="磐石关务二期"),
        ],
    )

    parent = client.get(BASE, params={"group_path": "磐石关务"}).json()
    assert parent["total"] == 3
    assert {item["title"] for item in parent["data"]} == {
        "父模块用例",
        "子模块用例",
        "孙模块用例",
    }

    child = client.get(BASE, params={"group_path": "磐石关务/回执"}).json()
    assert child["total"] == 2

    # 前缀相同的兄弟模块不能被误命中
    other = client.get(BASE, params={"group_path": "磐石关务二期"}).json()
    assert other["total"] == 1


def test_list_filters_ungrouped(client):
    # 请求级 group_path 置空，避免回落到 _bulk_import 的默认分组
    _bulk_import(
        client,
        cases=[
            _case_payload(title="有模块", group_path="磐石关务"),
            _case_payload(title="无模块", group_path=None),
        ],
        group_path=None,
    )
    ungrouped = client.get(BASE, params={"group_path": ""}).json()
    assert ungrouped["total"] == 1
    assert ungrouped["data"][0]["title"] == "无模块"


def test_groups_endpoint_returns_paths_with_counts(client):
    _bulk_import(
        client,
        cases=[
            _case_payload(title="a", group_path="磐石关务/回执"),
            _case_payload(title="b", group_path="磐石关务/回执"),
            _case_payload(title="c", group_path="磐石关务/回执/新增"),
            _case_payload(title="d", group_path="swgd-param"),
            _case_payload(title="e", group_path=None),
        ],
        group_path=None,
    )
    groups = client.get(f"{BASE}/groups").json()["data"]
    by_path = {item["path"]: item for item in groups}

    # 父级路径被补齐（磐石关务本身没有直属用例）
    assert set(by_path) == {
        "磐石关务",
        "磐石关务/回执",
        "磐石关务/回执/新增",
        "swgd-param",
    }
    assert by_path["磐石关务"]["direct_count"] == 0
    assert by_path["磐石关务"]["total_count"] == 3
    assert by_path["磐石关务/回执"]["direct_count"] == 2
    assert by_path["磐石关务/回执"]["total_count"] == 3
    assert by_path["磐石关务/回执"]["parent_path"] == "磐石关务"
    assert by_path["swgd-param"]["parent_path"] is None


def test_stats_counts_modules(client):
    _bulk_import(
        client,
        cases=[
            _case_payload(title="a", group_path="磐石关务/回执"),
            _case_payload(title="b", group_path="swgd-param"),
            _case_payload(title="c", group_path=None),
        ],
        group_path=None,
    )
    stats = client.get(f"{BASE}/stats").json()["data"]
    assert stats["total"] == 3
    # 只统计实际登记在用例上的模块路径
    assert stats["group_count"] == 2


def test_update_moves_case_between_groups(client):
    created = client.post(BASE, json=_case_payload(title="改模块")).json()["data"]
    assert created["group_path"] == "swgd-param/1. 码表"

    updated = client.put(
        f"{BASE}/{created['id']}", json={"group_path": " 磐石关务 // 回执 "}
    )
    assert updated.status_code == 200
    # 分组路径统一收紧斜杠与空白
    assert updated.json()["data"]["group_path"] == "磐石关务/回执"

    cleared = client.put(f"{BASE}/{created['id']}", json={"group_path": ""})
    assert cleared.json()["data"]["group_path"] is None


def test_update_rejects_invalid_case_type_on_edit(client):
    created = client.post(BASE, json=_case_payload(title="非法场景")).json()["data"]
    response = client.put(f"{BASE}/{created['id']}", json={"case_type": "unknown"})
    assert response.status_code == 422


def test_batch_move_to_group(client, db_session):
    first = client.post(BASE, json=_case_payload(title="移动A")).json()["data"]
    second = client.post(BASE, json=_case_payload(title="移动B")).json()["data"]

    response = client.post(
        f"{BASE}/batch-move",
        json={"case_ids": [first["id"], second["id"]], "group_path": "磐石关务"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["moved"] == 2
    db_session.expire_all()
    assert (
        db_session.query(ApiCaseRecord).filter_by(group_path="磐石关务").count() == 2
    )


def test_batch_move_requires_case_ids(client):
    response = client.post(f"{BASE}/batch-move", json={"case_ids": []})
    assert response.status_code == 422


def test_batch_delete(client, db_session):
    first = client.post(BASE, json=_case_payload(title="删除A")).json()["data"]
    second = client.post(BASE, json=_case_payload(title="删除B")).json()["data"]

    response = client.post(
        f"{BASE}/batch-delete", json={"case_ids": [first["id"], second["id"]]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["deleted"] == 2
    assert db_session.query(ApiCaseRecord).count() == 0


def test_export_respects_group_filter(client):
    _bulk_import(
        client,
        cases=[
            _case_payload(title="回执用例", group_path="磐石关务/回执"),
            _case_payload(title="报文用例", group_path="磐石关务/报文"),
        ],
    )
    response = client.get(f"{BASE}/export", params={"group_path": "磐石关务/回执"})
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook["接口用例"]
    titles = _column_values(sheet, "用例标题")
    assert titles == ["回执用例"]


def _merged_ranges(sheet) -> set[str]:
    return {str(item) for item in sheet.merged_cells.ranges}


def test_export_merges_same_group_and_interface(client):
    """同分组、同关联接口的用例要在导出里并成一块."""
    _bulk_import(
        client,
        cases=[
            _case_payload(title="反馈-正常", interface_name="01 新增反馈", group_path="A/Feedback"),
            _case_payload(title="反馈-异常", interface_name="01 新增反馈", group_path="A/Feedback"),
            _case_payload(title="回执-正常", interface_name="02 查询回执", group_path="A/Feedback"),
        ],
        interface_name=None,
        group_path=None,
    )
    response = client.get(f"{BASE}/export")
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook["接口用例"]
    merged = _merged_ranges(sheet)

    # 3 条用例同属一个分组 → 分组列合并成 A2:A4
    assert "A2:A4" in merged
    # 「01 新增反馈」两条连续 → 关联接口列合并成 B2:B3；「02 查询回执」只有一条不合并
    assert "B2:B3" in merged
    assert "B4:B4" not in merged

    # 合并后只有左上角保留值
    assert sheet["A2"].value == "A/Feedback"
    assert sheet["A3"].value is None
    assert sheet["B2"].value == "01 新增反馈"
    assert sheet["B4"].value == "02 查询回执"


def test_export_does_not_merge_across_groups(client):
    """同名关联接口但分组不同，不能跨分组合并."""
    _bulk_import(
        client,
        cases=[
            _case_payload(title="A组用例", interface_name="同名接口", group_path="模块一"),
            _case_payload(title="B组用例", interface_name="同名接口", group_path="模块二"),
        ],
        interface_name=None,
        group_path=None,
    )
    response = client.get(f"{BASE}/export")
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook["接口用例"]

    # 两个分组各只有一行，不应产生任何合并
    assert _merged_ranges(sheet) == set()
    assert _column_values(sheet, "关联接口") == ["同名接口", "同名接口"]


def test_export_skips_merge_for_ungrouped_and_empty_interface(client):
    """未分组 / 无关联接口不合并：值相同只是因为都没填."""
    _bulk_import(
        client,
        cases=[
            _case_payload(title="无模块A", interface_name=None, group_path=None),
            _case_payload(title="无模块B", interface_name=None, group_path=None),
        ],
        interface_name=None,
        group_path=None,
    )
    response = client.get(f"{BASE}/export")
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook["接口用例"]
    assert _merged_ranges(sheet) == set()
    # 未分组统一显示为「未分组」，便于阅读
    assert _column_values(sheet, "分组") == ["未分组", "未分组"]


def test_export_sorts_by_group_then_interface(client):
    """导出需按分组 → 关联接口排序，否则相同数据不连续、无法合并."""
    _bulk_import(
        client,
        cases=[
            _case_payload(title="Z组-接口2", interface_name="接口B", group_path="Z 模块"),
            _case_payload(title="A组-接口2", interface_name="接口B", group_path="A 模块"),
            _case_payload(title="Z组-接口1", interface_name="接口A", group_path="Z 模块"),
            _case_payload(title="A组-接口1", interface_name="接口A", group_path="A 模块"),
        ],
        interface_name=None,
        group_path=None,
    )
    response = client.get(f"{BASE}/export")
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook["接口用例"]

    assert _column_values(sheet, "分组") == ["A 模块", "Z 模块"]
    assert _column_values(sheet, "关联接口") == ["接口A", "接口B", "接口A", "接口B"]
    assert _column_values(sheet, "用例标题") == [
        "A组-接口1",
        "A组-接口2",
        "Z组-接口1",
        "Z组-接口2",
    ]
