"""批量执行必须使用变量管理中的全局/工作空间变量."""
from __future__ import annotations

import httpx
import pytest

from app.models.global_variable import GlobalVariable
from app.models.test_case import TestCase as ApiTestCase


@pytest.fixture
def workspace_case(db_session):
    project_id = "11111111-1111-1111-1111-111111111111"
    case = ApiTestCase(
        title="批量执行变量渲染",
        method="POST",
        url="{{contentProtocol}}://{{contentHost}}:{{contentPort}}/{{contentContext}}/{{version}}/apiService/queryPage",
        headers={"epToken": "{{epToken}}"},
        params={},
        body={"offset": 1},
        project_id=project_id,
        markers=["api", "postman_imported"],
    )
    db_session.add(case)
    db_session.flush()
    db_session.add_all(
        [
            GlobalVariable(
                name="contentProtocol",
                value="http",
                var_type="string",
                scope="workspace",
                project_id=project_id,
            ),
            GlobalVariable(
                name="contentHost",
                value="192.168.120.82",
                var_type="string",
                scope="workspace",
                project_id=project_id,
            ),
            GlobalVariable(
                name="contentPort",
                value="9002",
                var_type="string",
                scope="workspace",
                project_id=project_id,
            ),
            GlobalVariable(
                name="contentContext",
                # 变量值自带前导斜杠，验证不会产生 //path
                value="/swgdimapgateway/swgd-imap-content",
                var_type="string",
                scope="workspace",
                project_id=project_id,
            ),
            GlobalVariable(
                name="version",
                value="v1",
                var_type="string",
                scope="workspace",
                project_id=project_id,
            ),
            GlobalVariable(
                name="epToken",
                value="token-123",
                var_type="string",
                scope="workspace",
                project_id=project_id,
            ),
            # 其他项目的同名变量不应生效
            GlobalVariable(
                name="contentHost",
                value="should-not-be-used.example.com",
                var_type="string",
                scope="workspace",
                project_id="22222222-2222-2222-2222-222222222222",
            ),
        ]
    )
    db_session.commit()
    return case


def test_batch_execute_renders_workspace_variables(client, monkeypatch, workspace_case):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["eptoken"] = request.headers.get("eptoken")
        return httpx.Response(200, json={"code": 200})

    real_client = httpx.Client

    def patched_client(*args, **kwargs):
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(*args, **kwargs)

    monkeypatch.setattr("httpx.Client", patched_client)

    response = client.post(
        "/api/v1/test-cases/batch-execute",
        json={"case_ids": [workspace_case.id]},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert captured["url"] == (
        "http://192.168.120.82:9002/swgdimapgateway/swgd-imap-content/v1/apiService/queryPage"
    )
    assert captured["eptoken"] == "token-123"
    # 返回结果里展示的也应是渲染后的真实 URL
    assert data["results"][0]["url"] == captured["url"]
