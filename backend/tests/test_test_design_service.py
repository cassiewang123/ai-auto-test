"""AI 测试用例生成服务测试：测试点拆解、用例生成与多维评审."""

from __future__ import annotations

from app.services.test_design_service import (
    DEFAULT_REVIEW_DIMENSIONS,
    build_questions,
    generate_cases,
    generate_cases_by_rules,
    generate_test_points,
    generate_test_points_by_rules,
    review_cases,
)

FUNCTION_ITEMS = [
    {"module": "登录与认证", "points": ["用户名密码登录", "验证码校验"]},
    {"module": "项目管理", "points": ["创建项目"]},
]


def test_generate_test_points_covers_multiple_categories():
    points = generate_test_points_by_rules(
        "登录", "需求正文", FUNCTION_ITEMS, max_points=60
    )
    categories = {point.category for point in points}
    assert {"功能", "异常", "边界", "权限"} <= categories
    assert all(point.module for point in points)
    assert len(points) <= 60


def test_generate_test_points_deduplicates():
    points = generate_test_points_by_rules(
        "登录", "正文", FUNCTION_ITEMS, max_points=100
    )
    keys = [(point.module, point.point) for point in points]
    assert len(keys) == len(set(keys))


def test_generate_test_points_respects_max_points():
    many = [{"module": "模块", "points": [f"功能{n}" for n in range(50)]}]
    points = generate_test_points_by_rules("标题", "正文", many, max_points=12)
    assert len(points) <= 12


def test_generate_test_points_without_analysis_uses_text():
    points = generate_test_points_by_rules(
        "支付", "支付回调需要验签。支付超时需要重试。", None
    )
    assert points
    assert all(point.module for point in points)


def test_generate_test_points_with_empty_input_still_returns_core_point():
    points = generate_test_points_by_rules("空需求", "")
    assert len(points) == 1
    assert "核心流程" in points[0].point


def test_generate_cases_produces_steps_and_expected():
    points = generate_test_points_by_rules("登录", "正文", FUNCTION_ITEMS)
    cases = generate_cases_by_rules(points, "登录")
    assert cases
    for case in cases:
        assert case.title
        assert case.steps
        assert case.expected
        assert case.preconditions


def test_generate_cases_without_points_is_empty():
    assert generate_cases_by_rules([], "登录") == []


def test_generate_cases_respects_limit():
    points = generate_test_points_by_rules("登录", "正文", FUNCTION_ITEMS)
    cases = generate_cases_by_rules(points, "登录", max_cases=3)
    assert len(cases) == 3


def test_build_questions_reuses_clarifications():
    clarifications = [{"question": "密码规则是什么？", "reason": "缺失"}]
    questions = build_questions("登录", "正文", FUNCTION_ITEMS, clarifications)
    assert "密码规则是什么？" in questions


def test_build_questions_generates_generic_questions():
    questions = build_questions("登录", "简单的需求正文", FUNCTION_ITEMS, [])
    assert len(questions) >= 3
    assert all(question.endswith("？") for question in questions)


def test_generate_test_points_falls_back_to_rules_without_llm():
    points, engine = generate_test_points(
        "登录", "正文", FUNCTION_ITEMS, descriptions=["登录页提供输入框"]
    )
    assert engine == "rule"
    assert points


def test_generate_cases_falls_back_to_rules_without_llm():
    points = generate_test_points_by_rules("登录", "正文", FUNCTION_ITEMS)
    cases, engine = generate_cases(points, "登录", "正文")
    assert engine == "rule"
    assert cases


def _case_payload(**overrides):
    payload = {
        "title": "正常登录",
        "module": "登录与认证",
        "category": "功能",
        "priority": "P0",
        "preconditions": "已注册账号",
        "steps": ["打开登录页", "输入账号密码", "点击登录"],
        "expected": "登录成功并跳转首页",
        "trace_source": "用户名密码登录",
    }
    payload.update(overrides)
    return payload


def test_review_cases_scores_well_formed_cases():
    result = review_cases([_case_payload()], DEFAULT_REVIEW_DIMENSIONS)
    assert result["overall_score"] > 50
    assert result["dimension_scores"]["正确性"] == 100.0
    assert set(result["dimension_scores"]) == set(DEFAULT_REVIEW_DIMENSIONS)


def test_review_cases_flags_missing_expected():
    result = review_cases([_case_payload(expected="")])
    assert any(issue["level"] == "error" for issue in result["issues"])


def test_review_cases_flags_duplicate_titles():
    result = review_cases([_case_payload(), _case_payload()])
    assert any("重复" in issue["message"] for issue in result["issues"])


def test_review_cases_flags_missing_boundary_coverage():
    result = review_cases([_case_payload()])
    assert any("边界" in issue["message"] for issue in result["issues"])


def test_review_cases_weights_affect_score():
    cases = [_case_payload(), _case_payload(title="异常登录", category="异常")]
    low = review_cases(cases, {"覆盖完整性": 1, "正确性": 5})
    high = review_cases(cases, {"覆盖完整性": 5, "正确性": 1})
    assert low["overall_score"] != high["overall_score"]


def test_review_cases_handles_empty_list():
    result = review_cases([])
    assert result["overall_score"] == 0.0
    assert result["issues"] == []
