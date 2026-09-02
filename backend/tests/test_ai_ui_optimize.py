"""AI 加工 UI 录制步骤测试（基于文章方案：人工录制 + AI 加工）。

测试策略：
- 无 LLM 时走基于规则的 fallback，重点验证规则逻辑正确性。
- 有 LLM 时验证返回结构稳定（mock LLM）。
覆盖 3 个核心能力：
1. generate_ui_test_plan：把录制步骤加工为可读用例计划（步骤 + 预期）
2. optimize_ui_steps：补断言/补等待/去重/定位器标注，输出可稳定回归的步骤
3. suggest_ui_fix：失败后给出根因与定位器修复建议、修复后步骤
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.ai_service import AIService, LLMConfig


# ---------------------------------------------------------------------------
# 测试样本：模拟 Playwright codegen 人工录制产物
# ---------------------------------------------------------------------------
def _sample_raw_steps() -> list[dict]:
    """一份典型的登录+下单人工录制步骤（含重复与缺断言）。"""
    return [
        {"action": "navigate", "selector": "", "value": "http://robin.ep.local:30080/swgd-imap-user-center/#/login",
         "description": "导航到 登录页"},
        {"action": "input", "selector": "#username", "value": "admin",
         "description": "输入 用户名 \"admin\""},
        {"action": "input", "selector": "#password", "value": "123456",
         "description": "输入 密码 \"123456\""},
        {"action": "click", "selector": "#login-btn", "value": "",
         "description": "点击 登录 按钮"},
        {"action": "click", "selector": "#login-btn", "value": "",
         "description": "点击 登录 按钮"},  # 重复步骤
        {"action": "click", "selector": "li.nav-menu >> text=订单管理", "value": "",
         "description": "点击 订单管理"},
        {"action": "click", "selector": "text=新建订单", "value": "",
         "description": "点击 新建订单"},
    ]


_no_llm = LLMConfig(model="gpt-4", api_key="", base_url="")
_llm = LLMConfig(model="gpt-4", api_key="sk-test", base_url="")


# ---------------------------------------------------------------------------
# generate_ui_test_plan：用例计划生成
# ---------------------------------------------------------------------------
class TestGenerateUiTestPlan:
    def test_returns_plan_with_step_and_expected(self):
        """计划每条含 step/action/operation/expected 字段。"""
        service = AIService(config=_no_llm)
        result = service.generate_ui_test_plan(_sample_raw_steps())
        assert "plan" in result
        assert isinstance(result["plan"], list)
        assert len(result["plan"]) > 0
        for item in result["plan"]:
            assert "step" in item
            assert "action" in item
            assert "operation" in item
            assert "expected" in item

    def test_step_numbers_are_sequential(self):
        """计划步骤编号从 1 到 N 连续。"""
        service = AIService(config=_no_llm)
        plan = service.generate_ui_test_plan(_sample_raw_steps())["plan"]
        assert [p["step"] for p in plan] == list(range(1, len(plan) + 1))

    def test_input_plan_asserts_value_applied(self):
        """input 步骤的预期应体现输入值生效。"""
        service = AIService(config=_no_llm)
        plan = service.generate_ui_test_plan(_sample_raw_steps())["plan"]
        input_items = [p for p in plan if p["action"] == "input"]
        assert len(input_items) == 2
        assert all("admin" in input_items[0]["expected"] or "用户名" in input_items[0]["expected"]
                   for _ in [0])

    def test_navigate_plan_expects_loaded(self):
        """navigate 步骤预期为页面成功加载。"""
        service = AIService(config=_no_llm)
        plan = service.generate_ui_test_plan(_sample_raw_steps())["plan"]
        nav = plan[0]
        assert nav["action"] == "navigate"
        assert "加载" in nav["expected"] or "打开" in nav["expected"]

    def test_with_mock_llm_preserves_structure(self):
        """mock LLM 返回时结构仍稳定。"""
        service = AIService(config=_llm)
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = (
            '[{"step": 1, "action": "navigate", "operation": "打开登录页", '
            '"expected": "页面加载成功"}, '
            '{"step": 2, "action": "input", "operation": "输入用户名", '
            '"expected": "用户名已填入"}]'
        )
        mock_llm.invoke.return_value = mock_resp
        with patch.object(service, "_get_llm", return_value=mock_llm):
            result = service.generate_ui_test_plan(_sample_raw_steps())
        assert isinstance(result["plan"], list)
        assert len(result["plan"]) == 2
        assert result["plan"][0]["expected"] == "页面加载成功"


# ---------------------------------------------------------------------------
# optimize_ui_steps：录制步骤优化（补断言/补等待/去重/定位器标注）
# ---------------------------------------------------------------------------
class TestOptimizeUiSteps:
    def test_returns_optimized_steps(self):
        """返回优化后的步骤列表。"""
        service = AIService(config=_no_llm)
        result = service.optimize_ui_steps(_sample_raw_steps())
        assert "optimized_steps" in result
        assert isinstance(result["optimized_steps"], list)
        assert len(result["optimized_steps"]) > 0

    def test_removes_duplicate_consecutive_steps(self):
        """相邻重复步骤被去重。"""
        service = AIService(config=_no_llm)
        raw = _sample_raw_steps()
        raw_count = sum(1 for s in raw if s.get("selector") == "#login-btn")
        result = service.optimize_ui_steps(raw)
        opt = result["optimized_steps"]
        opt_count = sum(1 for s in opt if s.get("selector") == "#login-btn")
        assert opt_count == 1
        assert opt_count < raw_count

    def test_adds_assert_for_input_steps(self):
        """输入步骤后补充断言，确认条目可执行。"""
        service = AIService(config=_no_llm)
        result = service.optimize_ui_steps(_sample_raw_steps())
        opt = result["optimized_steps"]
        assert_actions = [s for s in opt if s.get("action") == "assert"]
        assert len(assert_actions) >= 1
        # 至少有一个断言针对输入框
        assert any(a.get("selector") == "#username" for a in assert_actions)

    def test_all_steps_are_executable_actions(self):
        """优化后所有步骤 action 均在执行引擎支持范围内。"""
        service = AIService(config=_no_llm)
        supported = {
            "navigate", "click", "input", "assert", "wait", "screenshot",
            "select", "press", "hover", "drag", "scroll", "upload", "download",
        }
        result = service.optimize_ui_steps(_sample_raw_steps())
        for step in result["optimized_steps"]:
            assert step["action"] in supported, f"不支持的 action: {step['action']}"

    def test_summary_contains_counts(self):
        """summary 统计含新增断言/等待与去重数量。"""
        service = AIService(config=_no_llm)
        result = service.optimize_ui_steps(_sample_raw_steps())
        summary = result.get("summary", {})
        assert "added_asserts" in summary
        assert "removed_duplicates" in summary
        assert summary["removed_duplicates"] >= 1


# ---------------------------------------------------------------------------
# suggest_ui_fix：失败定位器修复建议
# ---------------------------------------------------------------------------
class TestSuggestUiFix:
    def test_returns_root_cause_and_suggestions(self):
        """返回根因分类与修复建议列表。"""
        service = AIService(config=_no_llm)
        result = service.suggest_ui_fix(
            url="http://robin.ep.local:30080/",
            steps=_sample_raw_steps(),
            failed_step={"step": 3, "action": "click", "selector": "#login-btn"},
            error="Timeout 10000ms exceeded",
        )
        assert "root_cause" in result
        assert "category" in result
        assert "suggestions" in result
        assert isinstance(result["suggestions"], list)
        assert len(result["suggestions"]) > 0

    def test_locator_timeout_category(self):
        """超时/找不到元素归类为定位器问题。"""
        service = AIService(config=_no_llm)
        result = service.suggest_ui_fix(
            url="http://robin.ep.local:30080/",
            steps=_sample_raw_steps(),
            failed_step={"step": 3, "action": "click", "selector": "#login-btn"},
            error="TimeoutError: locator '#login-btn' not found after 10000ms",
        )
        assert result["category"] in ("locator_stale", "timeout")

    def test_suggests_text_fallback_locator(self):
        """给出基于文本的兜底定位器建议。"""
        service = AIService(config=_no_llm)
        result = service.suggest_ui_fix(
            url="http://robin.ep.local:30080/",
            steps=_sample_raw_steps(),
            failed_step={"step": 3, "action": "click", "selector": "#login-btn",
                          "description": "点击 登录 按钮"},
            error="Timeout 10000ms exceeded",
        )
        texts = " ".join(str(s) for s in result["suggestions"])
        # 示范替换为文本定位器
        assert any("text=" in str(s) for s in result["suggestions"]) or "text=" in texts

    def test_returns_repaired_steps(self):
        """可选返回修复后的步骤列表。"""
        service = AIService(config=_no_llm)
        result = service.suggest_ui_fix(
            url="http://robin.ep.local:30080/",
            steps=_sample_raw_steps(),
            failed_step={"step": 3, "action": "click", "selector": "#login-btn"},
            error="Timeout 10000ms exceeded",
        )
        assert "repaired_steps" in result
        assert isinstance(result["repaired_steps"], list)
        assert len(result["repaired_steps"]) > 0
        # 修复后步骤应包含对失败选择器的替换
        repaired = result["repaired_steps"]
        click_steps = [s for s in repaired if s.get("action") == "click"]
        assert all(s.get("selector") for s in click_steps)


# ---------------------------------------------------------------------------
# API 端点验证（无 LLM 走 fallback 规则）
# ---------------------------------------------------------------------------
class TestUiOptimizeApi:
    def test_ui_plan_endpoint(self, client):
        """POST /api/v1/ai/ui-plan 返回用例计划。"""
        resp = client.post(
            "/api/v1/ai/ui-plan",
            json={"steps": _sample_raw_steps()},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        plan = body["data"]["plan"]
        assert isinstance(plan, list)
        assert len(plan) > 0
        assert "expected" in plan[0]

    def test_optimize_ui_steps_endpoint(self, client):
        """POST /api/v1/ai/optimize-ui-steps 返回优化后步骤与统计。"""
        resp = client.post(
            "/api/v1/ai/optimize-ui-steps",
            json={"steps": _sample_raw_steps()},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert "optimized_steps" in data
        assert len(data["optimized_steps"]) > 0
        assert "summary" in data
        assert data["summary"]["removed_duplicates"] >= 1

    def test_suggest_ui_fix_endpoint(self, client):
        """POST /api/v1/ai/suggest-ui-fix 返回根因与建议。"""
        resp = client.post(
            "/api/v1/ai/suggest-ui-fix",
            json={
                "url": "http://robin.ep.local:30080/",
                "steps": _sample_raw_steps(),
                "failed_step": {
                    "step": 3,
                    "action": "click",
                    "selector": "#login-btn",
                    "description": "点击 登录 按钮",
                },
                "error": "TimeoutError: #login-btn not found",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert "root_cause" in data
        assert "category" in data
        assert isinstance(data["suggestions"], list)
        assert len(data["suggestions"]) > 0