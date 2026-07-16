"""Oracle schema and database URL compatibility tests."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects import oracle
from sqlalchemy.schema import CreateIndex, CreateTable

import app.models  # noqa: F401
from app.database import Base
from app.models.environment import Environment
from app.services.db_tester import DatabaseConfig, DatabaseTester


def test_all_tables_compile_for_oracle():
    dialect = oracle.dialect()
    for table in Base.metadata.sorted_tables:
        str(CreateTable(table).compile(dialect=dialect))
        for index in table.indexes:
            str(CreateIndex(index).compile(dialect=dialect))


def test_oracle_uses_clob_and_identity():
    dialect = oracle.dialect()
    environment_ddl = str(
        CreateTable(Base.metadata.tables["environments"]).compile(dialect=dialect)
    )
    event_ddl = str(
        CreateTable(Base.metadata.tables["job_events"]).compile(dialect=dialect)
    )
    assert "CLOB" in environment_ddl
    assert "IDENTITY" in event_ddl


def test_json_text_round_trip(db_session):
    environment = Environment(
        name="oracle-json",
        base_url="https://example.test",
        variables={"token": "abc", "flags": [True, False]},
        cookies=[],
    )
    db_session.add(environment)
    db_session.commit()
    db_session.expire_all()

    loaded = db_session.scalar(
        select(Environment).where(Environment.name == "oracle-json")
    )
    assert loaded.variables == {"token": "abc", "flags": [True, False]}


def test_database_tester_builds_oracle_service_url():
    url = DatabaseTester().build_url(
        DatabaseConfig(
            db_type="oracle",
            host="db.internal",
            port=1521,
            username="airetest",
            password="p@ss word",
            database="APP_PDB",
        )
    )
    assert url.startswith("oracle+oracledb://")
    assert "service_name=APP_PDB" in url
    assert "p%40ss+word" in url or "p%40ss%20word" in url
