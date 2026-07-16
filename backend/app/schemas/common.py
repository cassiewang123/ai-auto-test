"""通用响应模型与分页."""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ResponseBase(BaseModel):
    """统一响应包装."""

    code: int = 0
    message: str = "ok"


class DataResponse(ResponseBase, Generic[T]):
    """带数据的响应."""

    data: T | None = None


class PageResponse(ResponseBase, Generic[T]):
    """分页响应."""

    data: list[T] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class ErrorResponse(ResponseBase):
    """错误响应."""

    code: int = -1
    detail: str | None = None
