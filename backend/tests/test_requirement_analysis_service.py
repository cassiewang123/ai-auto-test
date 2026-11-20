"""需求分析规则引擎测试（无 LLM 兜底路径）."""

from __future__ import annotations

from app.services.requirement_analysis_service import (
    analyze_by_rules,
    analyze_requirement,
    render_markdown,
)

REQUIREMENT = """
用户登录功能：用户名与密码登录，支持记住密码。
用户密码长度 8-32 位，用户名唯一。
登录页面提供用户名、密码输入框与登录按钮。
验证码 4 位，有效期 60 秒。
项目创建后自动成为项目管理员，可以邀请成员。
需求管理支持上传文档并做分析等等。
"""


def test_analyze_by_rules_extracts_modules_and_points():
    result = analyze_by_rules("登录与需求管理", REQUIREMENT)
    assert result.engine == "rule"
    assert result.function_items
    modules = [item["module"] for item in result.function_items]
    assert any("登录" in module for module in modules)
    # 每个模块都有功能点且不超过上限
    for item in result.function_items:
        assert item["points"]
        assert len(item["points"]) <= 12


def test_analyze_by_rules_detects_ui_descriptions():
    result = analyze_by_rules("登录", REQUIREMENT)
    assert result.ui_descriptions
    assert any("登录页" in item["page"] for item in result.ui_descriptions)


def test_analyze_by_rules_reports_clarifications_for_vague_text():
    result = analyze_by_rules("登录", REQUIREMENT)
    questions = [item["question"] for item in result.clarifications]
    assert questions
    # 「等等」属于模糊表述，必须被识别
    assert any("等" in question for question in questions)


def test_analyze_by_rules_flags_missing_rules():
    result = analyze_by_rules("支付回调", "支付完成后回调通知，稍后处理。")
    joined = " ".join(item["question"] for item in result.clarifications)
    assert "校验" in joined or "规则" in joined
    assert "异常" in joined


def test_analyze_by_rules_handles_empty_text():
    result = analyze_by_rules("空需求", "")
    assert result.function_items == []
    # 空需求仍需给出澄清问题，提示补充正文
    assert result.clarifications


def test_render_markdown_contains_three_sections():
    result = analyze_by_rules("登录", REQUIREMENT)
    markdown = render_markdown(
        result.function_items, result.ui_descriptions, result.clarifications
    )
    assert "## 一、功能清单" in markdown
    assert "## 二、界面描述" in markdown
    assert "## 三、待澄清项" in markdown


def test_render_markdown_handles_empty_sections():
    markdown = render_markdown([], [], [])
    assert "未识别出功能模块" in markdown
    assert "未涉及界面交互" in markdown
    assert "未发现明显待澄清项" in markdown


def test_analyze_requirement_falls_back_to_rules_without_llm():
    """默认配置关闭外部 LLM，必须走规则引擎而不是报错."""
    result = analyze_requirement("登录", REQUIREMENT)
    assert result.engine == "rule"
    payload = result.to_dict()
    assert payload["markdown"]
    assert payload["function_items"] == result.function_items
