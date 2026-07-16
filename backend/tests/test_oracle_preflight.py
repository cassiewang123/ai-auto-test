"""Unit tests for the Oracle preflight tool without an Oracle dependency."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.sql.dml import Insert

from scripts.oracle_preflight import (
    EXPECTED_BUSINESS_TABLE_COUNT,
    EXPECTED_BUSINESS_TABLES,
    RuntimeWorkerInfo,
    SQLAlchemyOracleProbe,
    TransactionalSmokeResult,
    load_deployment_environment,
    load_expected_alembic_heads,
    main,
    run_preflight,
    run_static_preflight,
    run_worker_runtime_preflight,
    validate_oracle_url,
)


def _successful_probe() -> MagicMock:
    probe = MagicMock()
    probe.ping.return_value = "dialect=oracle server_version=23.0.0"
    probe.current_alembic_heads.return_value = {"c4e7a9b2d1f0"}
    probe.table_names.return_value = set(EXPECTED_BUSINESS_TABLES) | {"alembic_version"}
    probe.column_type.return_value = "CLOB"
    probe.transactional_smoke.return_value = TransactionalSmokeResult(
        payload_matches=True,
        identity_value=123,
        remaining_job_rows=0,
        remaining_event_rows=0,
    )
    return probe


def test_business_table_contract_contains_53_unique_names():
    assert len(EXPECTED_BUSINESS_TABLES) == EXPECTED_BUSINESS_TABLE_COUNT == 53
    assert {"execution_jobs", "job_events", "workflow_runs"} <= EXPECTED_BUSINESS_TABLES


def test_load_expected_alembic_head_without_database():
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_ini = backend_dir / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    repository_heads = set(ScriptDirectory.from_config(config).get_heads())

    assert repository_heads
    assert load_expected_alembic_heads(alembic_ini) == repository_heads


def test_validate_oracle_url_redacts_password():
    rendered = validate_oracle_url("oracle+oracledb://airetest:top-secret@db:1521/?service_name=APP")
    assert "top-secret" not in rendered
    assert "***" in rendered


def test_validate_oracle_url_rejects_other_dialects():
    with pytest.raises(ValueError, match=r"oracle\+oracledb"):
        validate_oracle_url("sqlite:///aitest.db")


def test_validate_oracle_url_requires_service_name():
    with pytest.raises(ValueError, match="service_name"):
        validate_oracle_url("oracle+oracledb://airetest:secret@db:1521/FREEPDB1")


@pytest.mark.parametrize("worker_topology", ["local", "distributed"])
def test_static_preflight_accepts_repository_development_example(
    worker_topology,
):
    repository_dir = Path(__file__).resolve().parents[2]
    environment = load_deployment_environment(
        repository_dir / ".env.oracle.example"
    )

    report = run_static_preflight(
        repository_dir / "docker-compose.yml",
        environment,
        worker_topology=worker_topology,
    )

    assert report.passed
    statuses = {check.name: check.status for check in report.checks}
    assert statuses == {
        "oracle_urls": "PASS",
        "schema_management": "PASS",
        "celery_redis": "PASS",
        "compose_worker_topology": "PASS",
        "compose_healthchecks": "PASS",
        "compose_dependency_gates": "PASS",
        "artifact_storage_boundary": "PASS",
        "deployment_secrets": "WARN",
    }
    topology_check = next(check for check in report.checks if check.name == "compose_worker_topology")
    assert f"selected={worker_topology}" in topology_check.detail


def test_compose_profiles_define_local_distributed_and_object_storage():
    repository_dir = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((repository_dir / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert "version" not in compose
    assert "profiles" not in services["worker-local"]
    assert services["worker-api"]["profiles"] == ["distributed"]
    assert services["worker-ui"]["profiles"] == ["distributed"]
    assert services["worker-performance"]["profiles"] == ["distributed"]
    assert services["minio"]["profiles"] == ["object-storage"]
    local_command = services["worker-local"]["command"]
    assert "--concurrency=1" in local_command
    assert all(
        marker in local_command
        for marker in (
            "CELERY_API_QUEUE",
            "CELERY_UI_QUEUE",
            "CELERY_PERFORMANCE_QUEUE",
        )
    )


def test_static_preflight_rejects_development_secrets_in_production():
    repository_dir = Path(__file__).resolve().parents[2]
    environment = load_deployment_environment(
        repository_dir / ".env.oracle.example"
    )
    environment["ENVIRONMENT"] = "production"

    report = run_static_preflight(
        repository_dir / "docker-compose.yml",
        environment,
    )

    assert not report.passed
    secret_check = next(check for check in report.checks if check.name == "deployment_secrets")
    assert secret_check.status == "FAIL"
    assert "SECRET_KEY" in secret_check.detail


def test_static_preflight_detects_artifact_mount_drift(tmp_path):
    repository_dir = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((repository_dir / "docker-compose.yml").read_text(encoding="utf-8"))
    compose["services"]["worker-api"]["volumes"].remove("uploads_data:/app/uploads")
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(
        yaml.safe_dump(compose, sort_keys=False),
        encoding="utf-8",
    )
    environment = load_deployment_environment(
        repository_dir / ".env.oracle.example"
    )

    report = run_static_preflight(compose_file, environment)

    assert not report.passed
    artifact_check = next(check for check in report.checks if check.name == "artifact_storage_boundary")
    assert artifact_check.status == "FAIL"
    assert "worker-api" in artifact_check.detail


def test_static_preflight_detects_distributed_profile_drift(tmp_path):
    repository_dir = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((repository_dir / "docker-compose.yml").read_text(encoding="utf-8"))
    compose["services"]["worker-api"]["profiles"] = []
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(
        yaml.safe_dump(compose, sort_keys=False),
        encoding="utf-8",
    )
    environment = load_deployment_environment(
        repository_dir / ".env.oracle.example"
    )

    report = run_static_preflight(
        compose_file,
        environment,
        worker_topology="distributed",
    )

    assert not report.passed
    topology_check = next(check for check in report.checks if check.name == "compose_worker_topology")
    assert topology_check.status == "FAIL"
    assert "worker-api" in topology_check.detail


def test_static_preflight_rejects_distributed_worker_with_extra_queue(
    tmp_path,
):
    repository_dir = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((repository_dir / "docker-compose.yml").read_text(encoding="utf-8"))
    compose["services"]["worker-api"]["command"] += ",${CELERY_UI_QUEUE:-airetest.ui}"
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(
        yaml.safe_dump(compose, sort_keys=False),
        encoding="utf-8",
    )
    environment = load_deployment_environment(
        repository_dir / ".env.oracle.example"
    )

    report = run_static_preflight(
        compose_file,
        environment,
        worker_topology="distributed",
    )

    topology_check = next(check for check in report.checks if check.name == "compose_worker_topology")
    assert topology_check.status == "FAIL"
    assert "CELERY_UI_QUEUE" in topology_check.detail


def test_static_preflight_cli_is_executable(capsys):
    repository_dir = Path(__file__).resolve().parents[2]

    exit_code = main(
        [
            "--static-only",
            "--compose-file",
            str(repository_dir / "docker-compose.yml"),
            "--env-file",
            str(repository_dir / ".env.oracle.example"),
        ]
    )

    assert exit_code == 0
    assert "RESULT: PASS WITH WARNINGS" in capsys.readouterr().out


def test_static_preflight_cli_accepts_distributed_topology(capsys):
    repository_dir = Path(__file__).resolve().parents[2]

    exit_code = main(
        [
            "--static-only",
            "--worker-topology",
            "distributed",
            "--compose-file",
            str(repository_dir / "docker-compose.yml"),
            "--env-file",
            str(repository_dir / ".env.oracle.example"),
        ]
    )

    assert exit_code == 0
    assert "selected=distributed" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("worker_topology", "workers"),
    [
        (
            "local",
            (
                RuntimeWorkerInfo(
                    name="local@container",
                    queues=frozenset(
                        {
                            "airetest.api",
                            "airetest.ui",
                            "airetest.performance",
                        }
                    ),
                    concurrency=1,
                ),
            ),
        ),
        (
            "distributed",
            (
                RuntimeWorkerInfo(
                    name="api@container",
                    queues=frozenset({"airetest.api"}),
                    concurrency=4,
                ),
                RuntimeWorkerInfo(
                    name="ui@container",
                    queues=frozenset({"airetest.ui"}),
                    concurrency=2,
                ),
                RuntimeWorkerInfo(
                    name="performance@container",
                    queues=frozenset({"airetest.performance"}),
                    concurrency=1,
                ),
            ),
        ),
    ],
)
def test_runtime_worker_preflight_accepts_supported_topologies(
    worker_topology,
    workers,
):
    probe = MagicMock()
    probe.workers.return_value = workers

    check = run_worker_runtime_preflight(probe, worker_topology)

    assert check.status == "PASS"
    assert f"selected={worker_topology}" in check.detail


def test_runtime_worker_preflight_rejects_wrong_local_concurrency():
    probe = MagicMock()
    probe.workers.return_value = (
        RuntimeWorkerInfo(
            name="local@container",
            queues=frozenset(
                {
                    "airetest.api",
                    "airetest.ui",
                    "airetest.performance",
                }
            ),
            concurrency=2,
        ),
    )

    check = run_worker_runtime_preflight(probe, "local")

    assert check.status == "FAIL"
    assert "concurrency=2 expected=1" in check.detail


def test_runtime_worker_preflight_rejects_local_worker_in_distributed_mode():
    probe = MagicMock()
    probe.workers.return_value = (
        RuntimeWorkerInfo(
            name="local@container",
            queues=frozenset(
                {
                    "airetest.api",
                    "airetest.ui",
                    "airetest.performance",
                }
            ),
            concurrency=1,
        ),
    )

    check = run_worker_runtime_preflight(probe, "distributed")

    assert check.status == "FAIL"
    assert "local_workers=1 expected=0" in check.detail


def test_run_preflight_reports_all_successful_checks_with_mock_probe():
    probe = _successful_probe()

    report = run_preflight(probe, {"c4e7a9b2d1f0"})

    assert report.passed
    assert {check.name: check.status for check in report.checks} == {
        "connection": "PASS",
        "alembic_head": "PASS",
        "business_tables": "PASS",
        "clob_json_column": "PASS",
        "clob_json_round_trip": "PASS",
        "identity_insert": "PASS",
        "transaction_rollback_cleanup": "PASS",
    }
    probe.transactional_smoke.assert_called_once_with()


def test_run_preflight_skips_writes_when_schema_is_incomplete():
    probe = _successful_probe()
    probe.table_names.return_value = {"execution_jobs", "job_events"}

    report = run_preflight(probe, {"c4e7a9b2d1f0"})

    assert not report.passed
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["business_tables"] == "FAIL"
    assert statuses["clob_json_column"] == "SKIP"
    assert statuses["transactional_smoke"] == "SKIP"
    probe.transactional_smoke.assert_not_called()


def test_run_preflight_reports_revision_mismatch():
    probe = _successful_probe()
    probe.current_alembic_heads.return_value = {"old-revision"}

    report = run_preflight(probe, {"c4e7a9b2d1f0"})

    assert not report.passed
    alembic_check = next(check for check in report.checks if check.name == "alembic_head")
    assert alembic_check.status == "FAIL"
    assert "old-revision" in alembic_check.detail


def test_transactional_smoke_only_inserts_and_always_rolls_back():
    engine = MagicMock()
    connection = MagicMock()
    transaction = MagicMock()
    transaction.is_active = True
    engine.connect.return_value.__enter__.return_value = connection
    connection.begin.return_value = transaction
    connection.scalar.side_effect = [
        json.dumps(
            {
                "probe": "oracle_preflight",
                "unicode": "Oracle JSON 往返",
                "nested": {"enabled": True, "values": [1, 2, 3]},
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        42,
        0,
        0,
    ]

    result = SQLAlchemyOracleProbe(engine).transactional_smoke()

    assert result.payload_matches
    assert result.identity_value == 42
    assert result.remaining_job_rows == result.remaining_event_rows == 0
    transaction.rollback.assert_called_once_with()
    statements = [call.args[0] for call in connection.execute.call_args_list]
    assert len(statements) == 2
    assert all(isinstance(statement, Insert) for statement in statements)


def test_transactional_smoke_rolls_back_after_insert_failure():
    engine = MagicMock()
    connection = MagicMock()
    transaction = MagicMock()
    transaction.is_active = True
    engine.connect.return_value.__enter__.return_value = connection
    connection.begin.return_value = transaction
    connection.execute.side_effect = RuntimeError("insert failed")
    connection.scalar.side_effect = [0, 0]

    with pytest.raises(RuntimeError, match="transaction was rolled back"):
        SQLAlchemyOracleProbe(engine).transactional_smoke()

    transaction.rollback.assert_called_once_with()
