"""Copy legacy AIRETEST SQLite data into an initialized Oracle schema."""
from __future__ import annotations

import argparse
import json
import os
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

from sqlalchemy import MetaData, Table, create_engine, func, inspect, select
from sqlalchemy.engine import URL, Connection, Engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate AIRETEST data from SQLite to Oracle.",
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        required=True,
        help="Path to the legacy SQLite database file.",
    )
    parser.add_argument(
        "--oracle-url",
        default=os.getenv("DATABASE_URL"),
        help="SQLAlchemy oracle+oracledb URL; defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--owner-user-id",
        default=None,
        help="User assigned as owner of legacy projects without memberships.",
    )
    parser.add_argument(
        "--allow-nonempty",
        action="store_true",
        help="Allow inserting into a target schema that already contains rows.",
    )
    parser.add_argument("--batch-size", type=int, default=200)
    return parser.parse_args()


def _decode_json_columns(row: dict[str, Any], table: Table) -> dict[str, Any]:
    from app.database_types import JSONText

    converted: dict[str, Any] = {}
    for column in table.columns:
        if column.name not in row:
            continue
        value = row[column.name]
        is_json = isinstance(column.type, JSONText)
        if is_json and isinstance(value, str):
            with suppress(json.JSONDecodeError):
                value = json.loads(value)
        if value == "" and not is_json:
            if column.nullable:
                # Oracle represents an empty string as NULL.
                value = None
            else:
                raise RuntimeError(
                    f"{table.name}.{column.name} contains an empty string "
                    "but is NOT NULL in Oracle"
                )
        converted[column.name] = value
    return converted


def _assert_target_empty(
    target: Engine,
    tables: list[Table],
    allow_nonempty: bool,
) -> None:
    if allow_nonempty:
        return
    with target.connect() as connection:
        nonempty = [
            table.name
            for table in tables
            if connection.scalar(select(func.count()).select_from(table))
        ]
    if nonempty:
        names = ", ".join(nonempty)
        raise RuntimeError(
            f"Oracle target is not empty ({names}). "
            "Use a fresh schema or pass --allow-nonempty explicitly."
        )


def _copy_table(
    source: Engine,
    target: Engine,
    source_table: Table,
    target_table: Table,
    batch_size: int,
) -> int:
    copied = 0
    with source.connect() as source_connection:
        missing_required = [
            column.name
            for column in target_table.columns
            if column.name not in source_table.c
            and not column.nullable
            and column.default is None
            and column.server_default is None
            and column.identity is None
        ]
        if missing_required:
            source_count = source_connection.scalar(
                select(func.count()).select_from(source_table)
            )
            if source_count:
                raise RuntimeError(
                    f"{source_table.name} is missing required target columns: "
                    f"{', '.join(missing_required)}"
                )

        result = source_connection.execute(select(source_table)).mappings()
        batch: list[dict[str, Any]] = []
        for row in result:
            batch.append(_decode_json_columns(dict(row), target_table))
            if len(batch) >= batch_size:
                with target.begin() as target_connection:
                    target_connection.execute(target_table.insert(), batch)
                copied += len(batch)
                batch.clear()
        if batch:
            with target.begin() as target_connection:
                target_connection.execute(target_table.insert(), batch)
            copied += len(batch)
    return copied


def _choose_owner(
    connection: Connection,
    users: Table,
    requested_user_id: str | None,
) -> str | None:
    if requested_user_id:
        exists = connection.scalar(
            select(func.count()).select_from(users).where(users.c.id == requested_user_id)
        )
        if not exists:
            raise RuntimeError(f"Owner user does not exist: {requested_user_id}")
        return requested_user_id
    owner_id = connection.scalar(
        select(users.c.id)
        .where(users.c.is_superuser.is_(True))
        .order_by(users.c.created_at)
        .limit(1)
    )
    if owner_id:
        return cast(str, owner_id)
    return cast(
        str | None,
        connection.scalar(
            select(users.c.id).order_by(users.c.created_at).limit(1)
        ),
    )


def _bootstrap_project_members(
    target: Engine,
    owner_user_id: str | None,
) -> int:
    from app.database import Base

    projects = Base.metadata.tables["projects"]
    users = Base.metadata.tables["users"]
    members = Base.metadata.tables["project_members"]

    with target.begin() as connection:
        owner_id = _choose_owner(connection, users, owner_user_id)
        project_ids = list(connection.scalars(select(projects.c.id)))
        if project_ids and not owner_id:
            raise RuntimeError(
                "Projects were migrated but no user exists for owner membership."
            )
        inserted = 0
        for project_id in project_ids:
            exists = connection.scalar(
                select(func.count()).select_from(members).where(
                    members.c.project_id == project_id
                )
            )
            if exists:
                continue
            connection.execute(
                members.insert().values(
                    project_id=project_id,
                    user_id=owner_id,
                    role="owner",
                    created_by=owner_id,
                )
            )
            inserted += 1
        return inserted


def main() -> None:
    args = parse_args()
    sqlite_path = args.sqlite.expanduser().resolve()
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")
    if not args.oracle_url or not args.oracle_url.startswith("oracle+oracledb://"):
        raise ValueError("--oracle-url must use the oracle+oracledb dialect")
    if args.batch_size < 1:
        raise ValueError("--batch-size must be positive")

    os.environ["DATABASE_URL"] = args.oracle_url

    import app.models  # noqa: F401
    from app.database import Base

    source_url = URL.create("sqlite", database=str(sqlite_path))
    source = create_engine(source_url)
    target = create_engine(args.oracle_url, pool_pre_ping=True)

    try:
        source_metadata = MetaData()
        source_metadata.reflect(bind=source)
        target_table_names = set(inspect(target).get_table_names())
        missing_target = [
            table.name
            for table in Base.metadata.sorted_tables
            if table.name not in target_table_names
        ]
        if missing_target:
            raise RuntimeError(
                "Oracle schema is incomplete; run alembic upgrade head first. "
                f"Missing: {', '.join(missing_target)}"
            )

        target_tables = list(Base.metadata.sorted_tables)
        _assert_target_empty(target, target_tables, args.allow_nonempty)

        total = 0
        for target_table in target_tables:
            source_table = source_metadata.tables.get(target_table.name)
            if source_table is None:
                print(f"SKIP {target_table.name}: not present in SQLite")
                continue
            copied = _copy_table(
                source,
                target,
                source_table,
                target_table,
                args.batch_size,
            )
            total += copied
            print(f"COPY {target_table.name}: {copied}")

        bootstrapped = _bootstrap_project_members(target, args.owner_user_id)
        print(f"DONE rows={total} project_members_created={bootstrapped}")
    finally:
        source.dispose()
        target.dispose()


if __name__ == "__main__":
    main()
