"""AI 加工录制步骤接入统一任务中心.

覆盖：
- JobCreate schema 接受 ai_ui_optimize 任务类型
- 支持携带 config.steps 创建任务（无 resource_id 时从请求 project 解析）
- JobService._run 正确派发并调用 AIService 产出计划 + 优化步骤
- 任务终态 succeeded，结果（计划/优化步骤）落库到 config._result_metrics 或 artifact

说明：任务编排测试通过 fake AIService 使执行确定且不依赖外部 LLM/API Key，
真实 AI 加工算法逻辑由 test_ai_ui_optimize.py / test_ai_service.py 单独覆盖。
"""
from __future__ import annotations

import pytest

from app.services.execution.job_service import JobService
from app.schemas.job import JobCreate


def _sample_steps() -> list[dict]:
    return [
        {"action": "navigate", "selector": "", "value": "http://robin.ep.local/#/login",
         "description": "导航到 登录页"},
        {"action": "input", "selector": "#username", "value": "admin",
         "description": "输入 用户名 \"admin\""},
        {"action": "input", "selector": "#password", "value": "123456",
         "description": "输入 密码 \"123456\""},
        {"action": "click", "selector": "#login-btn", "value": "",
         "description": "点击 登录 按钮"},
        {"action": "click", "selector": "#login-btn", "value": "",
         "description": "点击 登录 按钮"},  # 待去重
    ]


class _FakeAIService:
    """确定性的 AI 加工替身，避免测试触发真实 LLM 调用。"""

    def generate_ui_test_plan(self, steps: list[dict]) -> dict:
        return {"plan": [
            {"step": 1, "action": "navigate", "operation": "导航到登录页",
             "expected": "页面成功加载"},
        ], "source": "fake"}

    def optimize_ui_steps(self, steps: list[dict]) -> dict:
        return {
            "optimized_steps": [
                {"action": "navigate", "selector": "", "value": "",
                 "description": "导航到登录页"},
            ],
            "summary": {"added_asserts": 1, "added_waits": 1, "removed_duplicates": 1},
            "source": "fake",
        }


@pytest.fixture(autouse=True)
def _patch_ai_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """将 JobService._run_ai_ui_optimize 内引入的 AIService 替换为 fake。"""
    monkeypatch.setattr("app.services.ai_service.AIService", _FakeAIService)


class TestAiUiOptimizeJobSchema:
    def test_job_create_accepts_ai_ui_optimize_type(self):
        """JobCreate schema 允许 ai_ui_optimize。"""
        payload = JobCreate(
            job_type="ai_ui_optimize",
            config={"steps": _sample_steps()},
            project_id="p1",
        )
        assert payload.job_type == "ai_ui_optimize"
        assert payload.config["steps"]

    def test_job_create_allows_steps_without_resource_id(self):
        """AI 任务可不绑定 resource_id，仅携带 config.steps。"""
        payload = JobCreate(
            job_type="ai_ui_optimize",
            config={"steps": _sample_steps()},
        )
        assert payload.resource_id is None


class TestAiUiOptimizeJobCreate:
    def test_create_via_api_returns_job(self, client):
        """通过 API 创建 ai_ui_optimize 任务返回任务对象。"""
        resp = client.post(
            "/api/v1/jobs",
            json={
                "job_type": "ai_ui_optimize",
                "config": {"steps": _sample_steps()},
                "project_id": "p1",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["job_type"] == "ai_ui_optimize"


class TestAiUiOptimizeJobExecution:
    def test_execute_job_runs_ai_ui_optimize_and_succeeds(self, db_session):
        """执行 ai_ui_optimize 任务应产出计划与优化步骤并终结 succeeded。"""
        service = JobService(db_session)
        job = service.create_job(
            job_type="ai_ui_optimize",
            config={"steps": _sample_steps()},
            created_by="u1",
        )
        assert job.status == "queued"
        finished = service.execute_job(job.id, worker_id="w-test")
        assert finished.status == "succeeded"

        # 执行结果 metrics 内含计划步数和优化统计
        config = finished.config or {}
        metrics = config.get("_result_metrics", {})
        assert metrics.get("added_asserts", 0) >= 1
        assert metrics.get("removed_duplicates", 0) >= 1

    def test_execute_job_empty_steps_fails(self, db_session):
        """空 steps 时任务应失败而非静默成功。"""
        service = JobService(db_session)
        job = service.create_job(
            job_type="ai_ui_optimize",
            config={"steps": []},
            created_by="u1",
        )
        finished = service.execute_job(job.id, worker_id="w-test")
        assert finished.status == "failed"

    def test_execute_job_produces_report_artifact(self, db_session):
        """执行成功应生成 JSON 报告产物，包含 plan 与 optimized_steps。"""
        service = JobService(db_session)
        job = service.create_job(
            job_type="ai_ui_optimize",
            config={"steps": _sample_steps()},
            created_by="u1",
        )
        from app.models.job_artifact import JobArtifact

        finished = service.execute_job(job.id, worker_id="w-test")
        artifacts = (
            db_session.query(JobArtifact)
            .filter(JobArtifact.job_id == job.id)
            .all()
        )
        assert finished.status == "succeeded"
        assert any(a.artifact_type == "report" for a in artifacts)


class TestAiUiOptimizeArtifactDownload:
    def test_download_artifact_via_api_returns_report_json(self, client, db_session):
        """通过产物下载端点读取 AI 加工报告 JSON 内容。"""
        # 确定性执行：直接调用 JobService.execute_job（避免 local 线程竞态）
        service = JobService(db_session)
        job = service.create_job(
            job_type="ai_ui_optimize",
            config={"steps": _sample_steps()},
            created_by="u1",
        )
        finished = service.execute_job(job.id, worker_id="w-test")
        assert finished.status == "succeeded"

        # 列出产物并定位 report
        arts_resp = client.get(f"/api/v1/jobs/{job.id}/artifacts")
        assert arts_resp.status_code == 200
        artifacts = arts_resp.json()["data"]
        report = next(
            (a for a in artifacts if a.get("artifact_type") == "report"),
            None,
        )
        assert report is not None, f"未找到 report 产物: {artifacts}"

        # 下载产物并解析 JSON
        art_resp = client.get(
            f"/api/v1/jobs/{job.id}/artifacts/{report['id']}"
        )
        assert art_resp.status_code == 200
        assert "json" in art_resp.headers.get("content-type", "").lower() or "json" in (
            art_resp.headers.get("content-disposition", "") or ""
        ).lower()
        content = art_resp.json()
        assert "plan" in content
        assert "optimized_steps" in content