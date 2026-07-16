"""统一异常定义与处理."""
from __future__ import annotations


class AppException(Exception):
    """应用基础异常."""

    def __init__(self, message: str, status_code: int = 400, detail: str | None = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class NotFoundError(AppException):
    """资源不存在."""

    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"{resource} '{resource_id}' 不存在",
            status_code=404,
        )


class ValidationError(AppException):
    """数据校验失败."""

    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message=message, status_code=422, detail=detail)


class AuthenticationError(AppException):
    """认证失败."""

    def __init__(self, message: str = "认证失败"):
        super().__init__(message=message, status_code=401)


class ForbiddenError(AppException):
    """权限不足."""

    def __init__(self, message: str = "权限不足"):
        super().__init__(message=message, status_code=403)
