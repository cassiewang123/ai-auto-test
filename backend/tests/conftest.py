"""后端测试共享 fixture：内存数据库 + 测试客户端."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import create_app
from app.models.user import User
from app.services.auth_service import get_current_user
import app.models  # noqa: F401  注册所有模型元数据


def _mock_current_user() -> User:
    """测试用 mock 超级管理员用户（无需 JWT 认证）。"""
    return User(
        id="test-admin-id",
        username="testadmin",
        email="admin@test.com",
        hashed_password="",
        is_active=True,
        is_superuser=True,
    )


@pytest.fixture(scope="function")
def db_engine():
    """每个测试函数使用独立的内存 SQLite 数据库."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """提供独立数据库 Session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """提供 FastAPI TestClient，注入测试数据库."""
    app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = _mock_current_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
