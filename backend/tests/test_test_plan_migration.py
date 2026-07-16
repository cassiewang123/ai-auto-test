"""Migration-level coverage for TestPlan project ownership backfill."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "2026_07_15_1210-c4e7a9b2d1f0_add_test_plan_project_ownership.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_plan_project_ownership_migration",
        MIGRATION_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_legacy_schema(connection) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "projects",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
    )
    sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
    )
    sa.Table(
        "test_cases",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=True),
    )
    sa.Table(
        "test_plans",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
    )
    sa.Table(
        "test_plan_items",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("test_case_id", sa.String(36), nullable=False),
    )
    metadata.create_all(connection)


def test_backfill_requires_every_plan_item_to_have_one_project(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    migration = _load_migration()

    with engine.begin() as connection:
        _create_legacy_schema(connection)
        connection.execute(
            sa.text(
                """
                INSERT INTO projects (id)
                VALUES ('project-a'), ('project-b')
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO test_cases (id, project_id)
                VALUES
                    ('case-a1', 'project-a'),
                    ('case-a2', 'project-a'),
                    ('case-b', 'project-b'),
                    ('case-null', NULL)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO test_plans (id, name)
                VALUES
                    ('plan-one-project', 'one project'),
                    ('plan-with-null', 'one project plus null'),
                    ('plan-mixed', 'mixed projects'),
                    ('plan-all-null', 'all null'),
                    ('plan-orphan', 'orphan item'),
                    ('plan-empty', 'empty')
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO test_plan_items (id, plan_id, test_case_id)
                VALUES
                    ('item-a1', 'plan-one-project', 'case-a1'),
                    ('item-a2', 'plan-one-project', 'case-a2'),
                    ('item-null-a', 'plan-with-null', 'case-a1'),
                    ('item-null-b', 'plan-with-null', 'case-null'),
                    ('item-mixed-a', 'plan-mixed', 'case-a1'),
                    ('item-mixed-b', 'plan-mixed', 'case-b'),
                    ('item-all-null', 'plan-all-null', 'case-null'),
                    ('item-orphan', 'plan-orphan', 'missing-case')
                """
            )
        )

        operations = Operations(MigrationContext.configure(connection))
        original_op = migration.op
        migration.op = operations
        try:
            migration.upgrade()
        finally:
            migration.op = original_op

        rows = dict(
            connection.execute(
                sa.text(
                    "SELECT id, project_id FROM test_plans ORDER BY id"
                )
            ).all()
        )

    engine.dispose()

    assert rows["plan-one-project"] == "project-a"
    assert rows["plan-with-null"] is None
    assert rows["plan-mixed"] is None
    assert rows["plan-all-null"] is None
    assert rows["plan-orphan"] is None
    assert rows["plan-empty"] is None
