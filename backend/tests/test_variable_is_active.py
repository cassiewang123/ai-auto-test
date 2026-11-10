"""变量启停开关：禁用后不参与执行变量合并."""
from __future__ import annotations

import app.models  # noqa: F401  注册模型元数据
from app.models.global_variable import GlobalVariable
from app.services.execution.variables import load_global_variables

BASE = "/api/v1/variables"


def test_variable_api_defaults_to_active(client):
    created = client.post(
        BASE,
        json={
            "name": "token",
            "value": "abc",
            "var_type": "string",
            "scope": "global",
        },
    )
    assert created.status_code == 200
    data = created.json()["data"]
    assert data["is_active"] is True

    var_id = data["id"]
    disabled = client.put(f"{BASE}/{var_id}", json={"is_active": False})
    assert disabled.status_code == 200
    assert disabled.json()["data"]["is_active"] is False

    listed = client.get(BASE).json()["data"]
    assert listed[0]["is_active"] is False


def test_disabled_variable_is_not_loaded_for_execution(client, db_session):
    project_id = "22222222-2222-2222-2222-222222222222"
    db_session.add_all(
        [
            GlobalVariable(
                name="enabledVar",
                value="on",
                var_type="string",
                scope="workspace",
                project_id=project_id,
                is_active=True,
            ),
            GlobalVariable(
                name="disabledVar",
                value="off",
                var_type="string",
                scope="workspace",
                project_id=project_id,
                is_active=False,
            ),
        ]
    )
    db_session.commit()

    variables = load_global_variables(db_session, project_id)
    assert variables["enabledVar"] == "on"
    assert "disabledVar" not in variables
