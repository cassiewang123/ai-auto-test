"""应用配置管理，基于 Pydantic Settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_ENCRYPTION_KEY = "B05PSgXbYda2gKpXbQ_2YvL5P4MzlSlRV03Kpd64NqU="
DEV_JWT_SECRET_KEY = "dev-secret-change-in-production"


class Settings(BaseSettings):
    """全局配置，从环境变量与 .env 文件加载."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用
    APP_NAME: str = "AI Test Platform"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"  # development | staging | production

    # CORS — 逗号分隔的允许源列表（生产环境必须显式配置，禁止 *）
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 默认轻量单机使用 SQLite；Oracle 完整模式通过 .env.oracle 显式覆盖。
    DATABASE_URL: str = "sqlite:///./airetest-lite.db"
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_RECYCLE_SECONDS: int = 1800
    SQLITE_BUSY_TIMEOUT_MS: int = 5000
    SQLITE_JOURNAL_MODE: Literal["delete", "wal"] = "wal"
    SQLITE_SYNCHRONOUS: Literal["off", "normal", "full", "extra"] = "normal"
    # 仅本地临时环境允许 create_all；正式环境必须使用 Alembic。
    AUTO_CREATE_SCHEMA: bool = False

    # Redis 仅用于可选的 Oracle/Celery 完整模式。
    REDIS_URL: str = "redis://localhost:6379/0"

    # 异步任务中心
    # auto: Celery 可用时投递 Celery，否则使用 TASK_FALLBACK_MODE
    # celery: 强制投递 Celery；local/eager: 本地后台/当前调用内执行
    TASK_DISPATCH_MODE: Literal["auto", "celery", "local", "eager"] = "local"
    TASK_FALLBACK_MODE: Literal["disabled", "local", "eager"] = "disabled"
    TASK_EAGER_IN_TESTS: bool = True
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""
    CELERY_API_QUEUE: str = "airetest.api"
    CELERY_UI_QUEUE: str = "airetest.ui"
    CELERY_PERFORMANCE_QUEUE: str = "airetest.performance"
    CELERY_TASK_ACKS_LATE: bool = True
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = 1
    CELERY_TERMINATE_SIGNAL: str = "SIGTERM"

    # JWT
    SECRET_KEY: str = DEV_JWT_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # 敏感字段认证加密。生产环境必须显式覆盖开发密钥。
    SECRET_ENCRYPTION_KEY: str = DEV_SECRET_ENCRYPTION_KEY
    SECRET_ENCRYPTION_KEY_VERSION: str = "v1"

    # LLM（可选）
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4"
    LLM_BASE_URL: str = ""

    # InfluxDB（可选）
    INFLUXDB_URL: str = ""
    INFLUXDB_TOKEN: str = ""
    INFLUXDB_ORG: str = ""
    INFLUXDB_BUCKET: str = "metrics"

    # SSRF 防护
    URL_ALLOW_PRIVATE: bool = True  # 开发环境允许访问私有地址
    URL_ALLOWED_DOMAINS: str = ""  # 逗号分隔的域名白名单
    URL_BLOCKED_DOMAINS: str = ""  # 逗号分隔的域名黑名单
    # 出站响应体大小上限（字节），默认 10MB
    URL_MAX_RESPONSE_SIZE: int = 10 * 1024 * 1024

    # 执行安全
    ALLOW_SYNC_EXECUTION: bool = True  # 生产环境应设为 False
    SCRIPT_EXECUTION_TIMEOUT: int = 30  # 脚本执行超时（秒）

    # 文件产物
    ARTIFACT_ROOT: Path = Path(".uploads")
    ALLOW_DIRECT_FILE_PATHS: bool = False

    # 项目根目录
    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    @model_validator(mode="after")
    def validate_production_settings(self) -> Settings:
        """Reject unsafe execution and secret settings in production."""
        if self.ENVIRONMENT.strip().lower() not in {"production", "prod"}:
            return self

        from app.services.security.secret_crypto import (
            SecretConfigurationError,
            SecretCrypto,
        )

        errors: list[str] = []
        if not self.SECRET_KEY or self.SECRET_KEY == DEV_JWT_SECRET_KEY:
            errors.append("Production requires an explicit SECRET_KEY")
        if (
            not self.SECRET_ENCRYPTION_KEY
            or self.SECRET_ENCRYPTION_KEY == DEV_SECRET_ENCRYPTION_KEY
        ):
            errors.append(
                "Production requires an explicit SECRET_ENCRYPTION_KEY"
            )
        else:
            try:
                SecretCrypto(
                    self.SECRET_ENCRYPTION_KEY,
                    self.SECRET_ENCRYPTION_KEY_VERSION,
                )
            except SecretConfigurationError as exc:
                errors.append(str(exc))

        if self.ALLOW_SYNC_EXECUTION:
            errors.append(
                "Production requires ALLOW_SYNC_EXECUTION=false"
            )
        if self.TASK_DISPATCH_MODE in {"local", "eager"}:
            errors.append(
                "Production TASK_DISPATCH_MODE must be 'auto' or 'celery'"
            )
        if self.TASK_FALLBACK_MODE != "disabled":
            errors.append(
                "Production requires TASK_FALLBACK_MODE=disabled"
            )

        if errors:
            raise ValueError(
                "Invalid production configuration: " + "; ".join(errors)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """返回单例 Settings."""
    return Settings()
