"""Cross-database SQLAlchemy types used by the application."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class JSONText(TypeDecorator):
    """Store JSON-compatible values as text.

    Oracle maps ``Text`` to CLOB, while SQLite and other supported databases
    use their regular text type. Serialization here keeps the ORM value as a
    Python dict/list without requiring Oracle's native JSON data type.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is None or not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            # Keep legacy rows readable while old JSON/text data is migrated.
            return value
