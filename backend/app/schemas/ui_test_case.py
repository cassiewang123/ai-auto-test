"""UI 测试用例的请求/响应模型."""
from __future__ import annotations

from pydantic import BaseModel


class UiTestCaseCreate(BaseModel):
    """创建 UI 测试用例."""

    title: str
    description: str | None = None
    url: str
    browser_type: str = "chrome"
    steps: list[dict] = []
    project_id: str | None = None
    is_active: bool = True
    retry_count: int = 0  # 失败重试次数（0=不重试）
    retry_interval: float = 2.0  # 重试间隔（秒）


class UiTestCaseUpdate(BaseModel):
    """更新 UI 测试用例（部分更新）."""

    title: str | None = None
    description: str | None = None
    url: str | None = None
    browser_type: str | None = None
    steps: list[dict] | None = None
    project_id: str | None = None
    is_active: bool | None = None
    retry_count: int | None = None
    retry_interval: float | None = None


class ExtractStepsRequest(BaseModel):
    """从用例中提取步骤组的请求体."""

    name: str
    description: str | None = None
    start_index: int = 0  # 起始步骤索引（含）
    end_index: int | None = None  # 结束步骤索引（不含），None 表示到末尾
    project_id: str | None = None


class StartRecordingRequest(BaseModel):
    """启动录屏请求."""

    url: str
    browser_type: str = "chrome"
