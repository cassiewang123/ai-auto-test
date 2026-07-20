"""执行引擎共享数据结构：定义引擎与后端之间的契约.

这些模型是测试执行的核心数据载体，被 test-engine 与 backend/services 共同使用。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RequestDefinition(BaseModel):
    """从 TestCase 转换而来的请求定义，供执行引擎消费."""

    method: str = "GET"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    body: dict | None = None
    graphql_query: str | None = None
    files: list[dict] | None = None
    # 变量提取规则
    extract_rules: list[dict] = Field(default_factory=list)
    # 超时（秒）
    timeout: float = 30.0


class ResponseData(BaseModel):
    """执行引擎捕获的响应数据."""

    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    elapsed: float = 0.0
    # 原始响应文本
    text: str = ""


class AssertionResult(BaseModel):
    """单条断言的执行结果."""

    assertion_type: str
    expression: str | None = None
    operator: str = "eq"
    expected: Any = None
    actual: Any = None
    passed: bool
    message: str = ""


class ExtractedVariable(BaseModel):
    """从响应中提取的变量."""

    name: str
    value: Any
    source: str = "body"


class ExecutionResult(BaseModel):
    """单条用例的完整执行结果."""

    test_case_id: str
    status: str  # passed / failed / skipped / error
    duration: float = 0.0
    request: RequestDefinition | None = None
    response: ResponseData | None = None
    assertion_results: list[AssertionResult] = Field(default_factory=list)
    extracted_variables: list[ExtractedVariable] = Field(default_factory=list)
    error_message: str | None = None
    error_traceback: str | None = None
    executed_at: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# API 入参模型（直接执行端点）
# ---------------------------------------------------------------------------
class PreRequest(BaseModel):
    """前置条件：在主请求之前执行的请求."""

    name: str = ""
    method: str = "GET"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    body: dict | None = None
    # 从该请求响应中提取变量，传递给后续请求
    extract_rules: list[dict] = Field(default_factory=list)


class ExecuteRequest(BaseModel):
    """直接执行请求的入参."""

    method: str = "GET"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    body: dict | None = None
    graphql_query: str | None = None
    extract_rules: list[dict] = Field(default_factory=list)
    assertions: list[dict] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    timeout: float = 30.0
    # 前置条件
    pre_requests: list[PreRequest] = Field(default_factory=list)
    # 文件上传（base64 编码，前端转换）
    files: list[dict] = Field(default_factory=list)
    # 会话 Cookie 列表：[{"name": "session", "value": "xxx"}]
    cookies: list[dict] = Field(default_factory=list)
    # 前置/后置脚本（Python 代码）
    pre_script: str | None = None
    post_script: str | None = None
    # 失败重试
    retry_count: int = Field(0, ge=0)
    retry_interval: float = Field(1.0, ge=0)
    project_id: str | None = None
    environment_id: str | None = None
