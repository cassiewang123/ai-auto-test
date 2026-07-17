"""SQLite connection reliability settings."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.database import configure_sqlite_engine


def test_sqlite_file_engine_enables_reliability_pragmas(tmp_path) -> None:
    database = tmp_path / "reliability.db"
    database_url = f"sqlite:///{database.as_posix()}"
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    configure_sqlite_engine(engine, database_url)

    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
        assert connection.execute(text("PRAGMA synchronous")).scalar_one() == 1

    engine.dispose()


def test_sqlite_engine_rejects_orphan_rows(tmp_path) -> None:
    database = tmp_path / "foreign-keys.db"
    database_url = f"sqlite:///{database.as_posix()}"
    engine = create_engine(database_url)
    configure_sqlite_engine(engine, database_url)

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE parents (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE children ("
                "id INTEGER PRIMARY KEY, "
                "parent_id INTEGER NOT NULL REFERENCES parents(id)"
                ")"
            )
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO children (id, parent_id) VALUES (1, 999)")
            )

    engine.dispose()


def test_memory_sqlite_keeps_supported_journal_mode() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    configure_sqlite_engine(engine, "sqlite://")

    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "memory"

    engine.dispose()


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"busy_timeout_ms": -1}, "busy timeout"),
        ({"journal_mode": "truncate"}, "journal mode"),
        ({"synchronous": "invalid"}, "synchronous mode"),
    ],
)
def test_sqlite_engine_rejects_invalid_pragma_settings(
    override: dict[str, object],
    message: str,
) -> None:
    engine = create_engine("sqlite://")

    with pytest.raises(ValueError, match=message):
        configure_sqlite_engine(engine, "sqlite://", **override)

    engine.dispose()
