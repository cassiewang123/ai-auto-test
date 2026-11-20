"""RAG 文本切分与关键词抽取测试."""

from app.services.rag_text_splitter import (
    extract_keywords,
    score_chunk,
    split_text,
    tokenize_query,
)

SAMPLE = """# 登录项目

## 用户登录

用户名与密码校验规则：用户名最小长度 6，最大长度 32；密码最小长度 8。

验证码 4 位，有效期 60 秒，刷新后旧验证码立即失效。

## 项目管理

创建项目需要填写项目名称与项目描述，创建者自动成为项目管理员。
"""


def test_split_fixed_window_respects_size_limit():
    chunks = split_text(SAMPLE * 3, "fixed_window", 200, 40)
    assert len(chunks) > 1
    # 句末回退可能让首块略短，但不允许溢出上限
    assert all(chunk.char_count <= 200 for chunk in chunks)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))


def test_split_fixed_window_covers_all_text():
    text = "订单创建后需要记录操作日志。" * 40
    chunks = split_text(text, "fixed_window", 120, 0)
    assert "".join(chunk.content for chunk in chunks) == text


def test_split_paragraph_keeps_paragraphs_intact():
    text = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
    chunks = split_text(text, "paragraph", 400)
    assert len(chunks) == 1
    assert "第一段内容。" in chunks[0].content


def test_split_by_heading_records_heading():
    chunks = split_text(SAMPLE, "heading", 400)
    headings = [chunk.heading for chunk in chunks if chunk.heading]
    assert "用户登录" in headings
    assert "项目管理" in headings


def test_split_by_heading_falls_back_without_headings():
    chunks = split_text("没有标题的纯文本内容。", "heading", 400)
    assert len(chunks) == 1


def test_split_text_handles_empty_and_tiny_input():
    assert split_text("", "fixed_window") == []
    tiny = split_text("短", "fixed_window", 50, 10)
    assert len(tiny) == 1
    assert tiny[0].content == "短"


def test_split_text_unknown_strategy_falls_back_to_fixed_window():
    chunks = split_text(SAMPLE, "unknown-strategy", 200, 20)
    assert chunks
    assert all(chunk.heading is None for chunk in chunks)


def test_split_overlap_larger_than_size_is_clamped():
    # 重叠不得大于分块大小，否则滑窗无法推进
    chunks = split_text("测试内容。" * 100, "fixed_window", 100, 500)
    assert len(chunks) > 1


def test_extract_keywords_ranks_frequent_tokens():
    keywords = extract_keywords("用户名校验规则 用户名长度 用户名唯一", 10)
    assert keywords
    assert "用户" in keywords or "户名" in keywords


def test_extract_keywords_empty_text():
    assert extract_keywords("") == []


def test_tokenize_query_splits_chinese_and_english():
    tokens = tokenize_query("登录接口 login API")
    assert "login" in tokens
    assert any("登录" in token or "录接" in token for token in tokens)


def test_tokenize_query_drops_stopwords():
    tokens = tokenize_query("这个系统的功能是什么")
    assert "这个" not in tokens
    assert "什么" not in tokens


def test_score_chunk_rewards_relevant_content():
    keywords = extract_keywords("用户名与密码校验规则：用户名最小长度 6")
    relevant = score_chunk(["用户名", "校验"], keywords, "用户名与密码校验规则：用户名最小长度 6")
    unrelated = score_chunk(["用户名", "校验"], keywords, "完全无关的支付回调说明")
    assert relevant > unrelated
    assert 0 <= unrelated <= 1
    assert relevant <= 1


def test_score_chunk_without_query_tokens_is_zero():
    assert score_chunk([], ["用户名"], "用户名") == 0.0
