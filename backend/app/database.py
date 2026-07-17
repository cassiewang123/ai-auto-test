"""数据库连接与 Session 管理."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

def configure_sqlite_engine(
    target_engine: Engine,
    database_url: str,
    *,
    busy_timeout_ms: int = 5000,
    journal_mode: str = "wal",
    synchronous: str = "normal",
) -> None:
    """Apply the local SQLite reliability settings to every connection."""
    if not database_url.startswith("sqlite"):
        return

    parsed_url = make_url(database_url)
    is_file_database = parsed_url.database not in {None, "", ":memory:"}
    normalized_journal_mode = journal_mode.strip().upper()
    normalized_synchronous = synchronous.strip().upper()
    if busy_timeout_ms < 0:
        raise ValueError("SQLite busy timeout must not be negative")
    if normalized_journal_mode not in {"DELETE", "WAL"}:
        raise ValueError("SQLite journal mode must be DELETE or WAL")
    if normalized_synchronous not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
        raise ValueError(
            "SQLite synchronous mode must be OFF, NORMAL, FULL or EXTRA"
        )

    @event.listens_for(target_engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
            if is_file_database:
                cursor.execute(
                    f"PRAGMA journal_mode={normalized_journal_mode}"
                )
                cursor.execute(
                    f"PRAGMA synchronous={normalized_synchronous}"
                )
        finally:
            cursor.close()


is_sqlite = settings.DATABASE_URL.startswith("sqlite")
connect_args = {}
if is_sqlite:
    connect_args = {
        "check_same_thread": False,
        "timeout": settings.SQLITE_BUSY_TIMEOUT_MS / 1000,
    }

engine_kwargs = {
    "connect_args": connect_args,
    "echo": settings.DATABASE_ECHO,
    "pool_pre_ping": True,
}
if not settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update(
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_recycle=settings.DATABASE_POOL_RECYCLE_SECONDS,
    )

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
configure_sqlite_engine(
    engine,
    settings.DATABASE_URL,
    busy_timeout_ms=settings.SQLITE_BUSY_TIMEOUT_MS,
    journal_mode=settings.SQLITE_JOURNAL_MODE,
    synchronous=settings.SQLITE_SYNCHRONOUS,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类."""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：提供数据库 Session 并自动关闭."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """创建所有表（测试与开发用）.

    注意：生产环境应使用 Alembic 管理数据库 schema，执行：
        cd backend && python -m alembic upgrade head
    而非调用 Base.metadata.create_all()（create_all 仅用于开发/测试初始化，
    无法跟踪已有 schema 的演进历史，也不支持降级）。
    """
    # 导入所有模型以便 Base.metadata 注册
    from app.models import (  # noqa: F401
        ai_invocation,
        api_token,
        audit_log,
        business_rule,
        call_history,
        change_log,
        contract,
        db_assertion,
        defect_integration,
        defect_pattern,
        environment,
        execution_job,
        global_variable,
        interface_knowledge,
        job_artifact,
        mock_config,
        notification_channel,
        notification_log,
        notification_rule,
        perf_metric,
        performance_result,
        performance_test,
        project,
        project_member,
        quality_gate,
        role,
        scheduled_task,
        step_library,
        test_case,
        test_data_set,
        test_plan,
        test_result,
        test_run_summary,
        ui_element,
        ui_locator,
        ui_test_case,
        ui_test_record,
        ui_test_suite,
        user,
        visual_baseline,
        webhook_config,
        workflow,
    )

    Base.metadata.create_all(bind=engine)
