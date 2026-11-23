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


# ---------------------------------------------------------------------------
# 句子清洗：噪声剔除与续行拼接
# ---------------------------------------------------------------------------
def test_sentences_drop_attachment_marker():
    from app.services.requirement_analysis_service import _sentences

    sentences = _sentences("【附件：需求文档.pdf】\n真实功能描述内容。")
    assert all("【附件" not in item for item in sentences)
    assert any("真实功能描述内容" in item for item in sentences)


def test_sentences_strip_urls_and_query_fragments():
    from app.services.requirement_analysis_service import _sentences

    text = (
        "报文参考：https://www.singlewindow.cn/#/documentDetail?cid=MFT-1\n"
        "需要增加excel导入功能。"
    )
    sentences = _sentences(text)
    joined = " ".join(sentences)
    assert "http" not in joined
    assert "cid=" not in joined
    assert any("需要增加excel导入功能" in item for item in sentences)


def test_sentences_drop_pure_label_lines():
    from app.services.requirement_analysis_service import _sentences

    sentences = _sentences("页面参照：\n真实内容描述。")
    assert all(item.strip() not in {"页面参照：", "页面参照:"} for item in sentences)


def test_sentences_drop_symbol_only_fragments():
    from app.services.requirement_analysis_service import _sentences

    sentences = _sentences("– 2 –\n真实内容描述。")
    assert all("–" not in item for item in sentences)


def test_sentences_merge_soft_wrapped_line():
    from app.services.requirement_analysis_service import _sentences

    sentences = _sentences("出境运输方式 对应excel中的出境运输\n方式代码需要转换。")
    # 被硬换行截断的两半应合并进同一句，而不是拆成两条功能点
    assert len(sentences) == 1
    assert "\n" not in sentences[0]
    assert "出境运输" in sentences[0]
    assert "方式代码需要转换" in sentences[0]


def test_sentences_do_not_merge_new_labeled_item():
    from app.services.requirement_analysis_service import _sentences

    text = "上一句没有结束\n页面集装箱信息： 集装箱编号 对应excel中的集装箱编号。"
    sentences = _sentences(text)
    assert any(item.startswith("页面集装箱信息") for item in sentences)


def test_sentences_do_not_merge_numbered_trajectory_items():
    from app.services.requirement_analysis_service import _sentences

    text = "换装地2为空的情况\n轨迹序号1 对应申报地海关代码。\n轨迹序号2 对应换装地1。"
    sentences = _sentences(text)
    trajectory = [item for item in sentences if "轨迹序号" in item]
    assert len(trajectory) == 2


def test_sentences_split_overlong_merged_text():
    from app.services.requirement_analysis_service import _sentences

    long_text = "第一项要求。" * 40
    sentences = _sentences(long_text)
    assert all(len(item) <= 200 for item in sentences)


def test_analysis_ignores_pdf_furniture_noise():
    """PDF 页眉页码与 URL 不应出现在功能清单里."""
    noisy = (
        "公司名 – 需求文档\n"
        "– 2\n"
        "【附件：doc.pdf】\n"
        "报文参考：https://example.com/a?b=1\n"
        "页面基本信息： 申报地海关代码 对应excel中的申报地海关代码。\n"
    )
    result = analyze_by_rules("多式联运", noisy)
    points_text = " ".join(
        point for item in result.function_items for point in item["points"]
    )
    assert "【附件" not in points_text
    assert "http" not in points_text
    assert "申报地海关代码" in points_text


def test_sentences_deduplicate_repeated_text():
    """同一句在需求描述与附件正文中重复出现时只保留一条."""
    from app.services.requirement_analysis_service import _sentences

    text = "需要增加excel导入功能。\n\n需要增加excel导入功能。"
    sentences = _sentences(text)
    assert len(sentences) == 1
    assert sentences[0] == "需要增加excel导入功能。"
