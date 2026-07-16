"""Safe Oracle deployment preflight and transactional smoke checks.

The write smoke inserts uniquely identified rows into ``execution_jobs`` and
``job_events`` inside one transaction. It never commits, updates, deletes, or
creates database objects. After rollback it opens a new connection and verifies
that neither probe row remains.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import yaml
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from dotenv import dotenv_values
from sqlalchemy import (
    Column,
    Identity,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    inspect,
    literal,
    select,
)
from sqlalchemy.engine import Engine, make_url

LOCAL_WORKER_SERVICE = "worker-local"
DISTRIBUTED_WORKER_SERVICES = (
    "worker-api",
    "worker-ui",
    "worker-performance",
)
WORKER_SERVICES = (LOCAL_WORKER_SERVICE, *DISTRIBUTED_WORKER_SERVICES)
APP_SERVICES = ("backend", *WORKER_SERVICES)
SCHEMA_MANAGED_SERVICES = ("migrate", *APP_SERVICES)
WORKER_TOPOLOGIES = frozenset({"local", "distributed"})
DEFAULT_CELERY_QUEUES = {
    "api": "airetest.api",
    "ui": "airetest.ui",
    "performance": "airetest.performance",
}
DEV_SECRET_ENCRYPTION_KEY = "B05PSgXbYda2gKpXbQ_2YvL5P4MzlSlRV03Kpd64NqU="
DEVELOPMENT_SECRET_VALUES = {
    "ORACLE_PASSWORD": {"oracle_dev"},
    "ORACLE_APP_PASSWORD": {"airetest_dev"},
    "MINIO_ROOT_PASSWORD": {"airetest_dev"},
    "SECRET_KEY": {
        "change-this-to-a-random-secret-key",
        "dev-secret-change-in-production",
    },
    "SECRET_ENCRYPTION_KEY": {DEV_SECRET_ENCRYPTION_KEY},
}
EXPECTED_BUSINESS_TABLES = frozenset(
    {
        "ai_feedback",
        "ai_invocations",
        "api_tokens",
        "assertion_rules",
        "audit_logs",
        "business_rules",
        "call_history",
        "contract_diffs",
        "contract_versions",
        "db_assertions",
        "defect_patterns",
        "defect_tickets",
        "environments",
        "execution_attempts",
        "execution_jobs",
        "global_variables",
        "interface_change_logs",
        "interface_knowledge",
        "job_artifacts",
        "job_events",
        "mock_configs",
        "notification_channels",
        "notification_logs",
        "notification_rules",
        "perf_metrics",
        "performance_results",
        "performance_tests",
        "project_members",
        "projects",
        "quality_gate_results",
        "quality_gates",
        "roles",
        "scheduled_tasks",
        "step_library",
        "test_cases",
        "test_data_sets",
        "test_plan_items",
        "test_plans",
        "test_results",
        "test_run_summaries",
        "ui_elements",
        "ui_locators",
        "ui_test_cases",
        "ui_test_records",
        "ui_test_suite_runs",
        "ui_test_suites",
        "user_roles",
        "users",
        "visual_baselines",
        "visual_diff_results",
        "webhook_configs",
        "workflow_definitions",
        "workflow_runs",
    }
)
EXPECTED_BUSINESS_TABLE_COUNT = 53

_SMOKE_METADATA = MetaData()
_EXECUTION_JOBS = Table(
    "execution_jobs",
    _SMOKE_METADATA,
    Column("id", String(36), primary_key=True),
    Column("job_type", String(32), nullable=False),
    Column("status", String(16), nullable=False),
    Column("priority", Integer, nullable=False),
    Column("timeout_seconds", Integer, nullable=False),
    Column("max_attempts", Integer, nullable=False),
    Column("attempt_count", Integer, nullable=False),
    Column("config", Text, nullable=False),
)
_JOB_EVENTS = Table(
    "job_events",
    _SMOKE_METADATA,
    Column("id", Integer, Identity(), primary_key=True),
    Column("job_id", String(36), nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("payload", Text, nullable=True),
)


@dataclass(frozen=True)
class TransactionalSmokeResult:
    """Observed values from the rollback-only write probe."""

    payload_matches: bool
    identity_value: int | None
    remaining_job_rows: int
    remaining_event_rows: int


@dataclass(frozen=True)
class RuntimeWorkerInfo:
    """One live Celery worker observed through inspect."""

    name: str
    queues: frozenset[str]
    concurrency: int | None


@dataclass(frozen=True)
class CheckResult:
    """One independently reported preflight check."""

    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class PreflightReport:
    """Complete preflight result."""

    checks: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(check.status in {"PASS", "WARN", "SKIP"} for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [asdict(check) for check in self.checks],
        }


class OracleProbe(Protocol):
    """Minimal database operations required by the pure check orchestrator."""

    def ping(self) -> str: ...

    def current_alembic_heads(self) -> set[str]: ...

    def table_names(self) -> set[str]: ...

    def column_type(self, table_name: str, column_name: str) -> str: ...

    def transactional_smoke(self) -> TransactionalSmokeResult: ...


class WorkerRuntimeProbe(Protocol):
    """Live Celery worker inventory required by runtime topology checks."""

    def workers(self) -> tuple[RuntimeWorkerInfo, ...]: ...


class CeleryRuntimeProbe:
    """Inspect live Celery workers without importing application settings."""

    def __init__(self, broker_url: str, *, timeout: float = 5.0):
        self.broker_url = broker_url
        self.timeout = timeout

    def workers(self) -> tuple[RuntimeWorkerInfo, ...]:
        try:
            from celery import Celery
        except ImportError as exc:
            raise RuntimeError("Celery is required for --check-worker-runtime") from exc

        app = Celery("airetest-preflight", broker=self.broker_url)
        try:
            inspector = app.control.inspect(timeout=self.timeout)
            ping = inspector.ping() or {}
            active_queues = inspector.active_queues() or {}
            stats = inspector.stats() or {}
        finally:
            app.close()

        workers: list[RuntimeWorkerInfo] = []
        for worker_name in sorted(ping):
            raw_queues = active_queues.get(worker_name) or []
            queues = frozenset(
                str(queue["name"]) for queue in raw_queues if isinstance(queue, Mapping) and queue.get("name")
            )
            raw_stats = stats.get(worker_name)
            raw_pool = raw_stats.get("pool", {}) if isinstance(raw_stats, Mapping) else {}
            raw_concurrency = raw_pool.get("max-concurrency") if isinstance(raw_pool, Mapping) else None
            try:
                concurrency = int(raw_concurrency) if raw_concurrency is not None else None
            except (TypeError, ValueError):
                concurrency = None
            workers.append(
                RuntimeWorkerInfo(
                    name=str(worker_name),
                    queues=queues,
                    concurrency=concurrency,
                )
            )
        return tuple(workers)


class SQLAlchemyOracleProbe:
    """Oracle probe backed by a SQLAlchemy engine."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def ping(self) -> str:
        if self.engine.dialect.name != "oracle":
            raise RuntimeError(f"Expected Oracle dialect, got {self.engine.dialect.name!r}")
        with self.engine.connect() as connection:
            value = connection.scalar(select(literal(1)))
            if value != 1:
                raise RuntimeError(f"Unexpected ping result: {value!r}")
            version = connection.dialect.server_version_info
        rendered_version = ".".join(str(part) for part in version) if version else "unknown"
        return f"dialect=oracle server_version={rendered_version}"

    def current_alembic_heads(self) -> set[str]:
        with self.engine.connect() as connection:
            context = MigrationContext.configure(connection)
            return set(context.get_current_heads())

    def table_names(self) -> set[str]:
        return {name.lower() for name in inspect(self.engine).get_table_names()}

    def column_type(self, table_name: str, column_name: str) -> str:
        columns = inspect(self.engine).get_columns(table_name)
        for column in columns:
            if str(column["name"]).lower() == column_name.lower():
                return type(column["type"]).__name__.upper()
        raise RuntimeError(f"Column not found: {table_name}.{column_name}")

    def transactional_smoke(self) -> TransactionalSmokeResult:
        job_id = f"pf-{uuid.uuid4().hex}"
        payload = {
            "probe": "oracle_preflight",
            "unicode": "Oracle JSON 往返",
            "nested": {"enabled": True, "values": [1, 2, 3]},
        }
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        identity_value: int | None = None
        payload_matches = False
        write_error: Exception | None = None

        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    _EXECUTION_JOBS.insert().values(
                        id=job_id,
                        job_type="preflight",
                        status="queued",
                        priority=0,
                        timeout_seconds=30,
                        max_attempts=1,
                        attempt_count=0,
                        config=payload_json,
                    )
                )
                loaded_payload = connection.scalar(
                    select(_EXECUTION_JOBS.c.config).where(_EXECUTION_JOBS.c.id == job_id)
                )
                payload_matches = isinstance(loaded_payload, str) and json.loads(loaded_payload) == payload

                connection.execute(
                    _JOB_EVENTS.insert().values(
                        job_id=job_id,
                        event_type="preflight",
                        sequence=1,
                        payload='{"probe":"oracle_preflight"}',
                    )
                )
                raw_identity = connection.scalar(select(_JOB_EVENTS.c.id).where(_JOB_EVENTS.c.job_id == job_id))
                identity_value = int(raw_identity) if raw_identity is not None else None
            except Exception as exc:
                write_error = exc
            finally:
                if transaction.is_active:
                    transaction.rollback()

        with self.engine.connect() as connection:
            remaining_job_rows = int(
                connection.scalar(
                    select(func.count()).select_from(_EXECUTION_JOBS).where(_EXECUTION_JOBS.c.id == job_id)
                )
                or 0
            )
            remaining_event_rows = int(
                connection.scalar(select(func.count()).select_from(_JOB_EVENTS).where(_JOB_EVENTS.c.job_id == job_id))
                or 0
            )

        if write_error is not None:
            raise RuntimeError("Transactional smoke failed; the transaction was rolled back") from write_error

        return TransactionalSmokeResult(
            payload_matches=payload_matches,
            identity_value=identity_value,
            remaining_job_rows=remaining_job_rows,
            remaining_event_rows=remaining_event_rows,
        )


def load_expected_alembic_heads(alembic_ini: Path) -> set[str]:
    """Load repository migration heads without connecting to a database."""

    ini_path = alembic_ini.expanduser().resolve()
    if not ini_path.is_file():
        raise FileNotFoundError(f"Alembic config not found: {ini_path}")
    config = Config(str(ini_path))
    config.set_main_option(
        "script_location",
        str((ini_path.parent / "alembic").resolve()),
    )
    return set(ScriptDirectory.from_config(config).get_heads())


def validate_oracle_url(database_url: str) -> str:
    """Validate the configured SQLAlchemy dialect and return a redacted URL."""

    url = make_url(database_url)
    if url.drivername != "oracle+oracledb":
        raise ValueError("Oracle preflight requires an oracle+oracledb SQLAlchemy URL")
    if not url.query.get("service_name"):
        raise ValueError("Oracle URL must include the service_name query parameter")
    return cast(str, url.render_as_string(hide_password=True))


def load_deployment_environment(env_file: Path) -> dict[str, str]:
    """Load one explicit dotenv file for reproducible static validation."""

    path = env_file.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Environment file not found: {path}")
    return {key: value for key, value in dotenv_values(path).items() if value is not None}


def load_compose_config(compose_file: Path) -> dict[str, Any]:
    """Parse a Compose source file without requiring the Docker CLI."""

    path = compose_file.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Compose file not found: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("services"), dict):
        raise ValueError("Compose file must contain a services mapping")
    return cast(dict[str, Any], loaded)


def _normalize_worker_topology(worker_topology: str) -> str:
    normalized = worker_topology.strip().lower()
    if normalized not in WORKER_TOPOLOGIES:
        raise ValueError(f"worker topology must be one of: {', '.join(sorted(WORKER_TOPOLOGIES))}")
    return normalized


def _service_environment(service: Mapping[str, Any]) -> dict[str, str]:
    raw_environment = service.get("environment", {})
    if isinstance(raw_environment, Mapping):
        return {str(key): "" if value is None else str(value) for key, value in raw_environment.items()}
    if isinstance(raw_environment, Sequence) and not isinstance(raw_environment, (str, bytes)):
        environment: dict[str, str] = {}
        for item in raw_environment:
            key, separator, value = str(item).partition("=")
            environment[key] = value if separator else ""
        return environment
    raise ValueError("Compose service environment must be a mapping or list")


def _service_volumes(service: Mapping[str, Any]) -> set[str]:
    raw_volumes = service.get("volumes", [])
    if not isinstance(raw_volumes, Sequence) or isinstance(raw_volumes, (str, bytes)):
        return set()
    return {str(volume) for volume in raw_volumes}


def _service_profiles(service: Mapping[str, Any]) -> set[str]:
    raw_profiles = service.get("profiles", [])
    if raw_profiles is None:
        return set()
    if not isinstance(raw_profiles, Sequence) or isinstance(raw_profiles, (str, bytes)):
        return set()
    return {str(profile) for profile in raw_profiles}


def _healthcheck_test(healthcheck: Mapping[str, Any]) -> str:
    raw_test = healthcheck.get("test", "")
    if isinstance(raw_test, Sequence) and not isinstance(raw_test, (str, bytes)):
        return " ".join(str(part) for part in raw_test)
    return str(raw_test)


def _dependency_condition(
    services: Mapping[str, Any],
    service_name: str,
    dependency_name: str,
) -> str | None:
    service = services.get(service_name)
    if not isinstance(service, Mapping):
        return None
    depends_on = service.get("depends_on", {})
    if not isinstance(depends_on, Mapping):
        return None
    dependency = depends_on.get(dependency_name)
    if isinstance(dependency, Mapping):
        condition = dependency.get("condition")
        return str(condition) if condition is not None else None
    return None


def _compose_worker_topology_result(
    compose: Mapping[str, Any],
    worker_topology: str,
) -> CheckResult:
    services = cast(Mapping[str, Any], compose["services"])
    issues: list[str] = []
    if "version" in compose:
        issues.append("obsolete top-level version field must be removed")

    local_worker = services.get(LOCAL_WORKER_SERVICE)
    if not isinstance(local_worker, Mapping):
        issues.append(f"{LOCAL_WORKER_SERVICE}:missing_service")
    else:
        if _service_profiles(local_worker):
            issues.append(f"{LOCAL_WORKER_SERVICE}:must_be_default")
        command = str(local_worker.get("command", ""))
        for marker in (
            "CELERY_API_QUEUE",
            "CELERY_UI_QUEUE",
            "CELERY_PERFORMANCE_QUEUE",
            "--hostname=local@%h",
            "--concurrency=1",
        ):
            if marker not in command:
                issues.append(f"{LOCAL_WORKER_SERVICE}:command_missing_{marker}")

    distributed_markers = {
        "worker-api": ("CELERY_API_QUEUE", "--hostname=api@%h"),
        "worker-ui": ("CELERY_UI_QUEUE", "--hostname=ui@%h"),
        "worker-performance": (
            "CELERY_PERFORMANCE_QUEUE",
            "--hostname=performance@%h",
        ),
    }
    all_queue_markers = {
        "CELERY_API_QUEUE",
        "CELERY_UI_QUEUE",
        "CELERY_PERFORMANCE_QUEUE",
    }
    for service_name, markers in distributed_markers.items():
        service = services.get(service_name)
        if not isinstance(service, Mapping):
            issues.append(f"{service_name}:missing_service")
            continue
        if _service_profiles(service) != {"distributed"}:
            issues.append(f"{service_name}:profiles_must_equal_distributed")
        command = str(service.get("command", ""))
        for marker in markers:
            if marker not in command:
                issues.append(f"{service_name}:command_missing_{marker}")
        unexpected_queue_markers = sorted(marker for marker in all_queue_markers - {markers[0]} if marker in command)
        if unexpected_queue_markers:
            issues.append(f"{service_name}:unexpected_queues={unexpected_queue_markers}")

    minio = services.get("minio")
    if not isinstance(minio, Mapping):
        issues.append("minio:missing_service")
    elif _service_profiles(minio) != {"object-storage"}:
        issues.append("minio:profiles_must_equal_object-storage")

    selected_services = [LOCAL_WORKER_SERVICE] if worker_topology == "local" else list(DISTRIBUTED_WORKER_SERVICES)
    detail = (
        f"selected={worker_topology} workers={selected_services}; "
        "default local and optional distributed/object-storage profiles are valid"
        if not issues
        else f"selected={worker_topology} issues={issues}"
    )
    return _result("compose_worker_topology", not issues, detail)


def _compose_healthcheck_result(services: Mapping[str, Any]) -> CheckResult:
    expected_markers = {
        "oracle": "healthcheck.sh",
        "redis": "redis-cli ping",
        "minio": "/minio/health/live",
        "backend": "/health/ready",
        "worker-local": "inspect ping",
        "worker-api": "inspect ping",
        "worker-ui": "inspect ping",
        "worker-performance": "inspect ping",
    }
    issues: list[str] = []
    required_fields = {"test", "interval", "timeout", "retries", "start_period"}
    for service_name, marker in expected_markers.items():
        service = services.get(service_name)
        if not isinstance(service, Mapping):
            issues.append(f"{service_name}:missing_service")
            continue
        healthcheck = service.get("healthcheck")
        if not isinstance(healthcheck, Mapping):
            issues.append(f"{service_name}:missing_healthcheck")
            continue
        missing_fields = sorted(required_fields - set(healthcheck))
        if missing_fields:
            issues.append(f"{service_name}:missing_{','.join(missing_fields)}")
        rendered_test = _healthcheck_test(healthcheck)
        if marker not in rendered_test:
            issues.append(f"{service_name}:test_missing_{marker}")
    detail = (
        "oracle, redis, minio, backend and celery workers have bounded probes" if not issues else f"issues={issues}"
    )
    return _result("compose_healthchecks", not issues, detail)


def _compose_dependency_result(services: Mapping[str, Any]) -> CheckResult:
    expected = {
        ("migrate", "oracle"): "service_healthy",
        ("backend", "migrate"): "service_completed_successfully",
        ("backend", "redis"): "service_healthy",
        ("frontend", "backend"): "service_healthy",
        ("worker-local", "migrate"): "service_completed_successfully",
        ("worker-local", "redis"): "service_healthy",
        ("worker-api", "migrate"): "service_completed_successfully",
        ("worker-api", "redis"): "service_healthy",
        ("worker-ui", "migrate"): "service_completed_successfully",
        ("worker-ui", "redis"): "service_healthy",
        ("worker-performance", "migrate"): "service_completed_successfully",
        ("worker-performance", "redis"): "service_healthy",
    }
    issues = []
    for (service_name, dependency_name), condition in expected.items():
        actual = _dependency_condition(services, service_name, dependency_name)
        if actual != condition:
            issues.append(f"{service_name}->{dependency_name}={actual!r}, expected={condition}")
    detail = "migration, Redis and backend readiness gate dependent services" if not issues else f"issues={issues}"
    return _result("compose_dependency_gates", not issues, detail)


def _artifact_boundary_result(services: Mapping[str, Any]) -> CheckResult:
    issues: list[str] = []
    expected_mount = "uploads_data:/app/uploads"
    for service_name in APP_SERVICES:
        service = services.get(service_name)
        if not isinstance(service, Mapping):
            issues.append(f"{service_name}:missing_service")
            continue
        environment = _service_environment(service)
        if environment.get("ARTIFACT_ROOT") != "/app/uploads":
            issues.append(f"{service_name}:ARTIFACT_ROOT")
        if environment.get("ALLOW_DIRECT_FILE_PATHS", "").lower() != "false":
            issues.append(f"{service_name}:ALLOW_DIRECT_FILE_PATHS")
        if expected_mount not in _service_volumes(service):
            issues.append(f"{service_name}:missing_{expected_mount}")
        forbidden = sorted(key for key in environment if key.startswith("S3_") or key.startswith("MINIO_"))
        if forbidden:
            issues.append(f"{service_name}:object_store_env={forbidden}")
        depends_on = service.get("depends_on", {})
        if isinstance(depends_on, Mapping) and "minio" in depends_on:
            issues.append(f"{service_name}:unexpected_minio_dependency")

    minio = services.get("minio")
    if not isinstance(minio, Mapping) or "minio_data:/data" not in _service_volumes(minio):
        issues.append("minio:missing_minio_data:/data")

    detail = (
        "Artifact uses shared uploads_data:/app/uploads; MinIO storage is isolated"
        if not issues
        else f"issues={issues}"
    )
    return _result("artifact_storage_boundary", not issues, detail)


def _oracle_url_result(environment: Mapping[str, str]) -> CheckResult:
    issues: list[str] = []
    rendered: list[str] = []
    parsed_urls = {}
    for name in ("DATABASE_URL", "COMPOSE_DATABASE_URL"):
        value = environment.get(name, "").strip()
        if not value:
            issues.append(f"{name}:missing")
            continue
        try:
            rendered.append(f"{name}={validate_oracle_url(value)}")
            parsed_urls[name] = make_url(value)
        except Exception as exc:
            issues.append(f"{name}:{exc}")

    compose_url = parsed_urls.get("COMPOSE_DATABASE_URL")
    app_user = environment.get("ORACLE_APP_USER")
    app_password = environment.get("ORACLE_APP_PASSWORD")
    if compose_url is not None:
        if compose_url.username != app_user:
            issues.append("COMPOSE_DATABASE_URL username != ORACLE_APP_USER")
        if compose_url.password != app_password:
            issues.append("COMPOSE_DATABASE_URL password != ORACLE_APP_PASSWORD")

    detail = f"issues={issues}" if issues else " ".join(rendered)
    return _result("oracle_urls", not issues, detail)


def _schema_management_result(
    services: Mapping[str, Any],
    environment: Mapping[str, str],
) -> CheckResult:
    issues: list[str] = []
    if environment.get("AUTO_CREATE_SCHEMA", "").strip().lower() != "false":
        issues.append("env:AUTO_CREATE_SCHEMA must be false")
    for service_name in SCHEMA_MANAGED_SERVICES:
        service = services.get(service_name)
        if not isinstance(service, Mapping):
            issues.append(f"{service_name}:missing_service")
            continue
        value = _service_environment(service).get("AUTO_CREATE_SCHEMA", "")
        if value.strip().lower() != "false":
            issues.append(f"{service_name}:AUTO_CREATE_SCHEMA must be false")
    detail = "Alembic is the only schema manager" if not issues else f"issues={issues}"
    return _result("schema_management", not issues, detail)


def _celery_redis_result(
    services: Mapping[str, Any],
    environment: Mapping[str, str],
) -> CheckResult:
    issues: list[str] = []
    if environment.get("TASK_DISPATCH_MODE") != "celery":
        issues.append("TASK_DISPATCH_MODE must be celery")
    if environment.get("TASK_FALLBACK_MODE") != "disabled":
        issues.append("TASK_FALLBACK_MODE must be disabled")
    for name in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        value = environment.get(name, "")
        if not value.startswith(("redis://", "rediss://")):
            issues.append(f"{name} must use redis:// or rediss://")

    queues = [
        environment.get("CELERY_API_QUEUE", ""),
        environment.get("CELERY_UI_QUEUE", ""),
        environment.get("CELERY_PERFORMANCE_QUEUE", ""),
    ]
    if any(not queue for queue in queues) or len(set(queues)) != len(queues):
        issues.append("Celery queue names must be non-empty and unique")

    expected_queue_markers = {
        "worker-local": (
            "CELERY_API_QUEUE",
            "CELERY_UI_QUEUE",
            "CELERY_PERFORMANCE_QUEUE",
        ),
        "worker-api": ("CELERY_API_QUEUE",),
        "worker-ui": ("CELERY_UI_QUEUE",),
        "worker-performance": ("CELERY_PERFORMANCE_QUEUE",),
    }
    for service_name in APP_SERVICES:
        service = services.get(service_name)
        if not isinstance(service, Mapping):
            issues.append(f"{service_name}:missing_service")
            continue
        service_environment = _service_environment(service)
        for name in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
            if service_environment.get(name) != "redis://redis:6379/0":
                issues.append(f"{service_name}:{name}")
        command = str(service.get("command", ""))
        for queue_marker in expected_queue_markers.get(service_name, ()):
            if queue_marker not in command:
                issues.append(f"{service_name}:command_missing_{queue_marker}")

    detail = (
        "Redis broker/backend and local/distributed Celery queue routing are aligned"
        if not issues
        else f"issues={issues}"
    )
    return _result("celery_redis", not issues, detail)


def run_worker_runtime_preflight(
    probe: WorkerRuntimeProbe,
    worker_topology: str,
    queue_names: Mapping[str, str] = DEFAULT_CELERY_QUEUES,
) -> CheckResult:
    """Verify live Celery workers match the selected Compose topology."""

    topology = _normalize_worker_topology(worker_topology)
    expected_queues = {role: queue_names.get(role, "").strip() for role in ("api", "ui", "performance")}
    if any(not queue for queue in expected_queues.values()):
        return CheckResult(
            "celery_runtime_topology",
            "FAIL",
            f"selected={topology} queue names must be non-empty",
        )
    if len(set(expected_queues.values())) != len(expected_queues):
        return CheckResult(
            "celery_runtime_topology",
            "FAIL",
            f"selected={topology} queue names must be unique",
        )

    try:
        workers = probe.workers()
    except Exception as exc:
        return _failed("celery_runtime_topology", exc)

    expected_queue_set = frozenset(expected_queues.values())
    managed_roles = {"local", "api", "ui", "performance"}
    observed: dict[str, list[RuntimeWorkerInfo]] = {role: [] for role in managed_roles}
    issues: list[str] = []
    ignored: list[str] = []
    for worker in workers:
        role = worker.name.split("@", 1)[0].lower()
        if role in managed_roles:
            observed[role].append(worker)
        elif worker.queues & expected_queue_set:
            issues.append(f"{worker.name}:unexpected_worker_for_managed_queues")
        else:
            ignored.append(worker.name)

    if topology == "local":
        local_workers = observed["local"]
        if len(local_workers) != 1:
            issues.append(f"local_workers={len(local_workers)} expected=1")
        else:
            local_worker = local_workers[0]
            if local_worker.queues != expected_queue_set:
                issues.append(
                    f"{local_worker.name}:queues={sorted(local_worker.queues)} expected={sorted(expected_queue_set)}"
                )
            if local_worker.concurrency != 1:
                issues.append(f"{local_worker.name}:concurrency={local_worker.concurrency} expected=1")
        for role in ("api", "ui", "performance"):
            if observed[role]:
                issues.append(f"{role}_workers={len(observed[role])} expected=0")
    else:
        if observed["local"]:
            issues.append(f"local_workers={len(observed['local'])} expected=0")
        for role, expected_queue in expected_queues.items():
            role_workers = observed[role]
            if len(role_workers) != 1:
                issues.append(f"{role}_workers={len(role_workers)} expected=1")
                continue
            worker = role_workers[0]
            if worker.queues != {expected_queue}:
                issues.append(f"{worker.name}:queues={sorted(worker.queues)} expected={[expected_queue]}")

    worker_summary = [
        {
            "name": worker.name,
            "queues": sorted(worker.queues),
            "concurrency": worker.concurrency,
        }
        for worker in workers
    ]
    detail = (
        f"selected={topology} workers={worker_summary} ignored={ignored}"
        if not issues
        else f"selected={topology} issues={issues} workers={worker_summary}"
    )
    return _result("celery_runtime_topology", not issues, detail)


def _deployment_secrets_result(
    environment: Mapping[str, str],
) -> CheckResult:
    required = {
        "ORACLE_PASSWORD",
        "ORACLE_APP_USER",
        "ORACLE_APP_PASSWORD",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "SECRET_KEY",
        "SECRET_ENCRYPTION_KEY",
    }
    missing = sorted(name for name in required if not environment.get(name, "").strip())
    development_defaults = sorted(
        name for name, unsafe_values in DEVELOPMENT_SECRET_VALUES.items() if environment.get(name) in unsafe_values
    )
    format_issues: list[str] = []
    encryption_key = environment.get("SECRET_ENCRYPTION_KEY", "")
    if encryption_key:
        try:
            decoded_key = base64.b64decode(
                encryption_key.encode("ascii"),
                altchars=b"-_",
                validate=True,
            )
            if len(decoded_key) != 32:
                format_issues.append("SECRET_ENCRYPTION_KEY must decode to 32 bytes")
        except Exception:
            format_issues.append("SECRET_ENCRYPTION_KEY must be URL-safe Base64")

    secret_key = environment.get("SECRET_KEY", "")
    if (
        secret_key
        and secret_key not in DEVELOPMENT_SECRET_VALUES["SECRET_KEY"]
        and len(secret_key.encode("utf-8")) < 32
    ):
        format_issues.append("SECRET_KEY must contain at least 32 bytes")

    mode = environment.get("ENVIRONMENT", "").strip().lower()
    protected_environment = mode not in {"development", "dev", "test", "testing"}
    risky = bool(missing or development_defaults)
    if format_issues or (risky and protected_environment):
        status = "FAIL"
    elif risky:
        status = "WARN"
    else:
        status = "PASS"
    detail = (
        f"environment={mode or '<missing>'} missing={missing}"
        f" development_defaults={development_defaults}"
        f" format_issues={format_issues}"
    )
    return CheckResult("deployment_secrets", status, detail)


def run_static_preflight(
    compose_file: Path,
    environment: Mapping[str, str],
    *,
    worker_topology: str = "local",
) -> PreflightReport:
    """Validate deployment files without connecting to Oracle or Docker."""

    topology = _normalize_worker_topology(worker_topology)
    compose = load_compose_config(compose_file)
    services = cast(Mapping[str, Any], compose["services"])
    checks = (
        _oracle_url_result(environment),
        _schema_management_result(services, environment),
        _celery_redis_result(services, environment),
        _compose_worker_topology_result(compose, topology),
        _compose_healthcheck_result(services),
        _compose_dependency_result(services),
        _artifact_boundary_result(services),
        _deployment_secrets_result(environment),
    )
    return PreflightReport(checks)


def _result(name: str, passed: bool, detail: str) -> CheckResult:
    return CheckResult(name=name, status="PASS" if passed else "FAIL", detail=detail)


def _failed(name: str, exc: Exception) -> CheckResult:
    return CheckResult(name=name, status="FAIL", detail=f"{type(exc).__name__}: {exc}")


def run_preflight(
    probe: OracleProbe,
    expected_heads: set[str],
    expected_tables: set[str] | frozenset[str] = EXPECTED_BUSINESS_TABLES,
    *,
    run_transactional_smoke: bool = True,
) -> PreflightReport:
    """Run checks against an injected probe so orchestration is mock-testable."""

    checks: list[CheckResult] = []
    try:
        checks.append(CheckResult("connection", "PASS", probe.ping()))
    except Exception as exc:
        checks.append(_failed("connection", exc))
        return PreflightReport(tuple(checks))

    try:
        current_heads = probe.current_alembic_heads()
        checks.append(
            _result(
                "alembic_head",
                current_heads == expected_heads,
                f"database={sorted(current_heads)} expected={sorted(expected_heads)}",
            )
        )
    except Exception as exc:
        checks.append(_failed("alembic_head", exc))

    tables_ready = False
    try:
        actual_tables = probe.table_names()
        missing = sorted(set(expected_tables) - actual_tables)
        extras = sorted(actual_tables - set(expected_tables) - {"alembic_version"})
        tables_ready = not missing and len(expected_tables) == EXPECTED_BUSINESS_TABLE_COUNT
        detail = (
            f"required={len(expected_tables)} present={len(expected_tables) - len(missing)}"
            f" missing={missing} extra_schema_tables={extras}"
        )
        checks.append(_result("business_tables", tables_ready, detail))
    except Exception as exc:
        checks.append(_failed("business_tables", exc))

    clob_ready = False
    if tables_ready:
        try:
            config_type = probe.column_type("execution_jobs", "config")
            clob_ready = config_type in {"CLOB", "NCLOB"}
            checks.append(
                _result(
                    "clob_json_column",
                    clob_ready,
                    f"execution_jobs.config={config_type}",
                )
            )
        except Exception as exc:
            checks.append(_failed("clob_json_column", exc))
    else:
        checks.append(
            CheckResult(
                "clob_json_column",
                "SKIP",
                "Required business tables are incomplete",
            )
        )

    if not run_transactional_smoke:
        checks.append(
            CheckResult(
                "transactional_smoke",
                "SKIP",
                "Disabled by --skip-transactional-smoke",
            )
        )
    elif not tables_ready or not clob_ready:
        checks.append(
            CheckResult(
                "transactional_smoke",
                "SKIP",
                "Schema prerequisites did not pass",
            )
        )
    else:
        try:
            smoke = probe.transactional_smoke()
            checks.extend(
                (
                    _result(
                        "clob_json_round_trip",
                        smoke.payload_matches,
                        "JSON payload matched after insert/select",
                    ),
                    _result(
                        "identity_insert",
                        smoke.identity_value is not None and smoke.identity_value > 0,
                        f"job_events.id={smoke.identity_value}",
                    ),
                    _result(
                        "transaction_rollback_cleanup",
                        smoke.remaining_job_rows == 0 and smoke.remaining_event_rows == 0,
                        (f"execution_jobs={smoke.remaining_job_rows} job_events={smoke.remaining_event_rows}"),
                    ),
                )
            )
        except Exception as exc:
            checks.append(_failed("transactional_smoke", exc))

    return PreflightReport(tuple(checks))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    backend_dir = Path(__file__).resolve().parent.parent
    repository_dir = backend_dir.parent
    parser = argparse.ArgumentParser(
        description="Run safe AIRETEST Oracle deployment preflight checks.",
    )
    parser.add_argument(
        "--oracle-url",
        default=os.getenv("DATABASE_URL"),
        help="oracle+oracledb SQLAlchemy URL; defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--alembic-ini",
        type=Path,
        default=backend_dir / "alembic.ini",
        help="Path to backend/alembic.ini.",
    )
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Validate Compose and dotenv deployment settings without a database.",
    )
    parser.add_argument(
        "--worker-topology",
        choices=sorted(WORKER_TOPOLOGIES),
        default="local",
        help="Expected Celery topology: default local worker or distributed profile.",
    )
    parser.add_argument(
        "--check-worker-runtime",
        action="store_true",
        help="Inspect live Celery workers after the Oracle runtime checks.",
    )
    parser.add_argument(
        "--celery-broker-url",
        help="Broker URL for --check-worker-runtime; defaults to dotenv/process environment.",
    )
    parser.add_argument(
        "--celery-inspect-timeout",
        type=float,
        default=5.0,
        help="Celery inspect timeout in seconds.",
    )
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=repository_dir / "docker-compose.yml",
        help="Compose source used by --static-only.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=repository_dir / ".env",
        help="Explicit dotenv source for static and worker runtime checks.",
    )
    parser.add_argument(
        "--skip-transactional-smoke",
        action="store_true",
        help="Run read-only checks and skip rollback-only insert validation.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable JSON report.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.static_only:
        try:
            environment = load_deployment_environment(args.env_file)
            report = run_static_preflight(
                args.compose_file,
                environment,
                worker_topology=args.worker_topology,
            )
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2

        if args.json:
            output = report.to_dict()
            output["compose_file"] = str(args.compose_file.expanduser().resolve())
            output["env_file"] = str(args.env_file.expanduser().resolve())
            output["worker_topology"] = args.worker_topology
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(f"Compose source: {args.compose_file.expanduser().resolve()}")
            print(f"Environment source: {args.env_file.expanduser().resolve()}")
            for check in report.checks:
                print(f"[{check.status}] {check.name}: {check.detail}")
            has_warnings = any(check.status == "WARN" for check in report.checks)
            if report.passed and has_warnings:
                print("RESULT: PASS WITH WARNINGS")
            else:
                print("RESULT: PASS" if report.passed else "RESULT: FAIL")
        return 0 if report.passed else 1

    if not args.oracle_url:
        print("ERROR: --oracle-url or DATABASE_URL is required", file=sys.stderr)
        return 2

    try:
        redacted_url = validate_oracle_url(args.oracle_url)
        expected_heads = load_expected_alembic_heads(args.alembic_ini)
        if len(EXPECTED_BUSINESS_TABLES) != EXPECTED_BUSINESS_TABLE_COUNT:
            raise RuntimeError(
                f"Oracle table contract is inconsistent: {len(EXPECTED_BUSINESS_TABLES)} names configured"
            )
        engine = create_engine(args.oracle_url, pool_pre_ping=True)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    try:
        report = run_preflight(
            SQLAlchemyOracleProbe(engine),
            expected_heads,
            run_transactional_smoke=not args.skip_transactional_smoke,
        )
    finally:
        engine.dispose()

    if args.check_worker_runtime:
        if args.celery_inspect_timeout <= 0:
            print("ERROR: --celery-inspect-timeout must be positive", file=sys.stderr)
            return 2
        runtime_environment: dict[str, str] = {}
        if args.env_file.expanduser().is_file():
            runtime_environment.update(load_deployment_environment(args.env_file))
        runtime_environment.update(os.environ)
        broker_url = (
            args.celery_broker_url
            or runtime_environment.get("CELERY_BROKER_URL")
            or runtime_environment.get("REDIS_URL")
        )
        if not broker_url:
            print(
                "ERROR: --celery-broker-url, CELERY_BROKER_URL or REDIS_URL is required",
                file=sys.stderr,
            )
            return 2
        queue_names = {
            "api": runtime_environment.get(
                "CELERY_API_QUEUE",
                DEFAULT_CELERY_QUEUES["api"],
            ),
            "ui": runtime_environment.get(
                "CELERY_UI_QUEUE",
                DEFAULT_CELERY_QUEUES["ui"],
            ),
            "performance": runtime_environment.get(
                "CELERY_PERFORMANCE_QUEUE",
                DEFAULT_CELERY_QUEUES["performance"],
            ),
        }
        worker_check = run_worker_runtime_preflight(
            CeleryRuntimeProbe(
                broker_url,
                timeout=args.celery_inspect_timeout,
            ),
            args.worker_topology,
            queue_names,
        )
        report = PreflightReport((*report.checks, worker_check))

    if args.json:
        output = report.to_dict()
        output["database_url"] = redacted_url
        if args.check_worker_runtime:
            output["worker_topology"] = args.worker_topology
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"Oracle target: {redacted_url}")
        for check in report.checks:
            print(f"[{check.status}] {check.name}: {check.detail}")
        print("RESULT: PASS" if report.passed else "RESULT: FAIL")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
