"""FastAPI 应用入口.

SEC-01 改造要点：
1. CORS 从 allow_origins=["*"] 改为可配置的显式源列表。
2. 所有业务路由统一注入 Depends(get_current_user) 鉴权依赖，
   仅 /auth（登录/注册）、/health 和 /ci/trigger（CI Token 独立鉴权）保持公开。
3. 生产环境（ENVIRONMENT != development）路由加载失败立即 sys.exit(1)，
   不再静默跳过。
"""
from __future__ import annotations

import importlib
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.exceptions import AppException
from app.services.auth_service import get_current_user
from app.services.security.log_sanitizer import SanitizingFilter

settings = get_settings()
logger = logging.getLogger(__name__)

# 需要统一 JWT 鉴权的业务路由模块（排除 auth 和 ci_cd）
# auth: login/register 需公开，/me 已自带 Depends(get_current_user)
# ci_cd: /trigger 使用 CI Token 独立鉴权，webhook 管理端点在文件内单独添加 JWT
# jobs: HTTP 端点在各自函数内已自带 Depends(get_current_user)；WebSocket
#       端点（/{id}/stream）不能使用 Depends（浏览器握手无法设置 Authorization
#       头），改为在端点内从查询参数 ?token= 手动验证 JWT，故不注入路由级依赖。
_PUBLIC_ROUTERS = {"app.api.v1.auth", "app.api.v1.ci_cd", "app.api.v1.jobs"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：按配置初始化本地开发数据库."""
    if settings.AUTO_CREATE_SCHEMA:
        from app.database import init_db

        init_db()
    yield


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例."""
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # --- SEC-01: 严格 CORS ---
    # 从配置解析允许的源列表，生产环境禁止使用 "*"
    cors_origins = [
        origin.strip()
        for origin in settings.CORS_ORIGINS.split(",")
        if origin.strip()
    ]
    if not cors_origins:
        cors_origins = ["http://localhost:5173"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    # SEC-09: 为 root logger 添加日志脱敏过滤器
    root_logger = logging.getLogger()
    # 避免重复添加过滤器
    if not any(isinstance(f, SanitizingFilter) for f in root_logger.filters):
        root_logger.addFilter(SanitizingFilter())

    # 全局异常处理
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": -1,
                "message": exc.message,
                "detail": exc.detail,
            },
        )

    # --- 健康检查（公开，无需鉴权）---
    @app.get("/health")
    async def health():
        return {"status": "ok", "app": settings.APP_NAME}

    @app.get("/health/live")
    async def health_live():
        """存活检查：进程是否响应."""
        return {"status": "alive"}

    @app.get("/health/ready")
    async def health_ready():
        """就绪检查：数据库等关键依赖是否可用."""
        try:
            from sqlalchemy import select

            from app.database import engine
            with engine.connect() as conn:
                conn.execute(select(1))
            return {"status": "ready", "database": "ok"}
        except Exception as e:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "error": str(e)},
            )

    # 注册路由
    _register_routers(app)

    return app


def _register_routers(app: FastAPI) -> None:
    """注册各 API 路由模块。

    SEC-01 改造：
    - 业务路由统一注入 Depends(get_current_user) 鉴权。
    - /auth 路由保持公开（login/register 需匿名访问，/me 自带鉴权）。
    - /ci 路由保持公开（/trigger 使用 CI Token 独立鉴权），
      webhook 管理端点在 ci_cd.py 内部单独添加 JWT 鉴权。
    - 生产环境路由加载失败立即退出，开发环境仅告警。
    """
    registered: list[str] = []
    failed: list[str] = []
    is_production = settings.ENVIRONMENT != "development"

    for module_path, attr, prefix in [
        ("app.api.v1.environments", "router", "/environments"),
        ("app.api.v1.test_cases", "router", "/test-cases"),
        # Phase 4 用例版本管理：与 test_cases 共用 /test-cases 前缀
        # 端点内自带 Depends(get_current_user) 以注入 user 用于 reviewer/approver
        ("app.api.v1.test_case_versions", "router", "/test-cases"),
        ("app.api.v1.test_plans", "router", "/test-plans"),
        ("app.api.v1.reports", "router", "/reports"),
        ("app.api.v1.report_export", "router", "/report-export"),
        ("app.api.v1.coverage", "router", "/coverage"),
        ("app.api.v1.scheduled_tasks", "router", "/scheduled-tasks"),
        ("app.api.v1.mock_service", "router", "/mock-service"),
        ("app.api.v1.change_logs", "router", "/change-logs"),
        ("app.api.v1.ai", "router", "/ai"),
        ("app.api.v1.execution", "router", "/execution"),
        ("app.api.v1.history", "router", "/history"),
        ("app.api.v1.import_api", "router", "/import"),
        ("app.api.v1.projects", "router", "/projects"),
        ("app.api.v1.capture", "router", "/capture"),
        ("app.api.v1.ui_test_cases", "router", "/ui-test-cases"),
        ("app.api.v1.ui_test_records", "router", "/ui-test-records"),
        ("app.api.v1.ui_test_suites", "router", "/ui-test-suites"),
        ("app.api.v1.ui_elements", "router", "/ui-elements"),
        # Phase 4 UI 定位器版本管理
        ("app.api.v1.ui_locators", "router", "/ui-locators"),
        ("app.api.v1.step_library", "router", "/step-library"),
        ("app.api.v1.visual_regression", "router", "/visual-regression"),
        # ui_junit 模块内部路径已含完整前缀
        ("app.api.v1.ui_junit", "router", ""),
        ("app.api.v1.performance_tests", "router", "/perf-tests"),
        ("app.api.v1.db_assertions", "router", "/db-assertions"),
        ("app.api.v1.knowledge", "router", "/knowledge"),
        # auth 路由保持公开（login/register 需匿名访问）
        ("app.api.v1.auth", "router", "/auth"),
        ("app.api.v1.users", "router", "/users"),
        ("app.api.v1.roles", "router", "/roles"),
        ("app.api.v1.api_tokens", "router", "/api-tokens"),
        # SEC-09: 审计日志查询（需超级管理员权限，权限在端点内校验）
        ("app.api.v1.audit_logs", "router", "/audit-logs"),
        # ci_cd 路由保持公开（/trigger 使用 CI Token 鉴权）
        ("app.api.v1.ci_cd", "router", "/ci"),
        ("app.api.v1.test_data", "router", "/test-data"),
        ("app.api.v1.notifications", "router", "/notifications"),
        ("app.api.v1.variables", "router", "/variables"),
        # 统一任务中心：HTTP 端点自带 JWT 鉴权，WebSocket 在端点内验证 token
        ("app.api.v1.jobs", "router", "/jobs"),
        # Phase 4：DAG 工作流 / 契约测试 / 质量门禁（均需 JWT 鉴权）
        ("app.api.v1.workflows", "router", "/workflows"),
        ("app.api.v1.contracts", "router", "/contracts"),
        ("app.api.v1.quality_gates", "router", "/quality-gates"),
        # Phase 5：AI 运营治理 / 缺陷集成（均需 JWT 鉴权）
        ("app.api.v1.ai_ops", "router", "/ai-ops"),
        ("app.api.v1.defects", "router", "/defects"),
    ]:
        try:
            mod = importlib.import_module(module_path)
            router = getattr(mod, attr)
            # SEC-01: 业务路由统一注入 JWT 鉴权依赖
            # auth 和 ci_cd 路由保持公开（各自内部有独立鉴权逻辑）
            auth_deps = []
            if module_path not in _PUBLIC_ROUTERS:
                auth_deps = [Depends(get_current_user)]
            app.include_router(
                router,
                prefix=f"{settings.API_V1_PREFIX}{prefix}",
                dependencies=auth_deps,
            )
            registered.append(module_path)
        except Exception as exc:
            failed.append(module_path)
            logging.exception(
                "Failed to register router %s: %s: %s",
                module_path, type(exc).__name__, exc,
            )

    # SEC-01: 生产环境路由加载失败立即退出
    if failed:
        if is_production:
            logger.error(
                "生产环境路由加载失败，退出进程。失败模块: %s",
                ", ".join(failed),
            )
            sys.exit(1)
        else:
            logger.warning(
                "开发环境部分路由加载失败（已跳过）: %s",
                ", ".join(failed),
            )

    if registered:
        app.state.registered_routers = registered
        app.state.failed_routers = failed


app = create_app()
