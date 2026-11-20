"""RAG 文本切分与关键词抽取.

文档「知识库管理」的分块参数配置落地：
- 固定窗口（按字符长度滑窗）：适合叙事型需求/设计文档；
- 按段落：适合条目清晰的业务说明；
- 按标题：适合带 Markdown 标题的技术文档。

关键词抽取用于无向量依赖的检索打分：把中文按二元组切分、英文按单词切分，
过滤停用词后统计词频，得到分块的关键词集合。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 分块大小边界：文档建议 400-1500，过小片段化、过大噪声多
MIN_CHUNK_SIZE = 100
MAX_CHUNK_SIZE = 4000
# 关键词数量上限（每个分块）
MAX_KEYWORDS = 40

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z0-9_]{2,}")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;\n])")

# 中文常见停用词（高频但无区分度，检索时会淹没有效信号）
_STOPWORDS = {
    "这个", "那个", "我们", "他们", "可以", "需要", "进行", "以及", "并且",
    "但是", "如果", "因为", "所以", "已经", "一个", "什么", "怎么", "时候",
    "这些", "那些", "对于", "通过", "根据", "由于", "其中", "然后", "同时",
    "不是", "没有", "不会", "必须", "应该", "支持", "提供", "实现", "包括",
    "用户", "系统", "功能", "页面", "相关", "对应", "以下", "如下",
    "上述", "本文", "介绍", "说明", "描述", "内容", "方式", "情况", "问题",
    "the", "and", "for", "with", "that", "this", "from", "are", "was",
    "has", "have", "will", "can", "must", "should", "not", "but", "all",
}


@dataclass
class Chunk:
    """一个文本分块."""

    index: int
    content: str
    heading: str | None = None

    @property
    def char_count(self) -> int:
        return len(self.content)


def normalize_whitespace(text: str) -> str:
    """压缩空白，保留段落分隔."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clamp_chunk_size(chunk_size: int) -> int:
    return max(MIN_CHUNK_SIZE, min(MAX_CHUNK_SIZE, int(chunk_size)))


def _clamp_overlap(chunk_size: int, chunk_overlap: int) -> int:
    """重叠必须小于分块大小，否则滑窗无法推进."""
    overlap = max(0, int(chunk_overlap))
    return min(overlap, max(0, chunk_size - 1))


def split_fixed_window(
    text: str, chunk_size: int = 400, chunk_overlap: int = 80
) -> list[Chunk]:
    """固定窗口滑窗切分，尽量在句末断开以保留语义."""
    text = normalize_whitespace(text)
    if not text:
        return []

    size = _clamp_chunk_size(chunk_size)
    overlap = _clamp_overlap(size, chunk_overlap)

    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        # 未到文末时，回退到最近的句末标点，避免把一句话切断；
        # 但回退过多会退化成极短分块，因此只在回退不超过半窗时才采纳。
        if end < len(text):
            boundary = _last_sentence_boundary(text[start:end])
            if boundary > size // 2:
                end = start + boundary

        piece = text[start:end].strip()
        if piece:
            chunks.append(Chunk(index=len(chunks), content=piece))

        if end >= len(text):
            break
        # 下一窗起点回退 overlap，保证跨窗口语义连续
        start = max(end - overlap, start + 1)

    return chunks


def _last_sentence_boundary(piece: str) -> int:
    for marker in ("。", "！", "？", "；", ".", "!", "?", ";", "\n"):
        pos = piece.rfind(marker)
        if pos >= 0:
            return pos + len(marker)
    return -1


def split_paragraph(text: str, chunk_size: int = 400) -> list[Chunk]:
    """按段落聚合切分：段落不拆开，超长段落回退到窗口切分."""
    text = normalize_whitespace(text)
    if not text:
        return []

    size = _clamp_chunk_size(chunk_size)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_len = 0

    def flush() -> None:
        nonlocal buffer, buffer_len
        if buffer:
            chunks.append(Chunk(index=len(chunks), content="\n\n".join(buffer)))
            buffer = []
            buffer_len = 0

    for paragraph in paragraphs:
        if len(paragraph) > size:
            flush()
            for sub in split_fixed_window(paragraph, size, 0):
                chunks.append(Chunk(index=len(chunks), content=sub.content))
            continue
        if buffer_len + len(paragraph) + 2 > size:
            flush()
        buffer.append(paragraph)
        buffer_len += len(paragraph) + 2
    flush()
    return chunks


def split_by_heading(text: str, chunk_size: int = 400) -> list[Chunk]:
    """按 Markdown 标题切分，标题作为分块元数据."""
    text = normalize_whitespace(text)
    if not text:
        return []

    size = _clamp_chunk_size(chunk_size)
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return split_paragraph(text, size)

    chunks: list[Chunk] = []
    # 首个标题之前的内容
    preamble = text[: matches[0].start()].strip()
    if preamble:
        for sub in split_paragraph(preamble, size):
            chunks.append(Chunk(index=len(chunks), content=sub.content))

    for position, match in enumerate(matches):
        heading = match.group(2).strip()[:500]
        body_start = match.end()
        body_end = (
            matches[position + 1].start()
            if position + 1 < len(matches)
            else len(text)
        )
        body = text[body_start:body_end].strip()
        section = f"{heading}\n{body}" if body else heading
        if len(section) <= size:
            chunks.append(
                Chunk(index=len(chunks), content=section, heading=heading)
            )
        else:
            for sub in split_paragraph(section, size):
                chunks.append(
                    Chunk(
                        index=len(chunks),
                        content=sub.content,
                        heading=heading,
                    )
                )
    return chunks


def split_text(
    text: str,
    strategy: str = "fixed_window",
    chunk_size: int = 400,
    chunk_overlap: int = 80,
) -> list[Chunk]:
    """按策略切分文本，未知策略回退到固定窗口."""
    if strategy == "paragraph":
        return split_paragraph(text, chunk_size)
    if strategy == "heading":
        return split_by_heading(text, chunk_size)
    return split_fixed_window(text, chunk_size, chunk_overlap)


# ---------------------------------------------------------------------------
# 关键词抽取
# ---------------------------------------------------------------------------
def extract_keywords(text: str, limit: int = MAX_KEYWORDS) -> list[str]:
    """抽取关键词：中文二元组 + 英文单词，按词频降序."""
    if not text:
        return []

    lowered = text.lower()
    counts: dict[str, int] = {}

    for word in _WORD_RE.findall(lowered):
        if word in _STOPWORDS or len(word) < 2:
            continue
        counts[word] = counts.get(word, 0) + 1

    # 中文按相邻字二元组切分，无需分词依赖
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", lowered):
        for i in range(len(sequence) - 1):
            token = sequence[i : i + 2]
            if token in _STOPWORDS:
                continue
            counts[token] = counts.get(token, 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [token for token, _ in ranked[:limit]]


def tokenize_query(query: str) -> list[str]:
    """把查询语句切成检索词（中文二元组 + 英文单词去停用词）."""
    query = (query or "").lower()
    tokens: list[str] = []
    seen: set[str] = set()

    for word in _WORD_RE.findall(query):
        if word in _STOPWORDS or word in seen:
            continue
        seen.add(word)
        tokens.append(word)

    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        candidates = (
            [sequence]
            if len(sequence) == 2
            else [sequence[i : i + 2] for i in range(len(sequence) - 1)]
        )
        for token in candidates:
            if token in _STOPWORDS or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return tokens


def score_chunk(query_tokens: list[str], chunk_keywords: list[str], content: str) -> float:
    """计算查询与分块的相关度.

    打分 = 命中关键词数 / 查询词数 * 0.7 + 命中关键词频次占比 * 0.2 +
    原文直接包含查询词的加成 0.1。范围 0-1，便于设置召回阈值。
    """
    if not query_tokens:
        return 0.0

    keyword_set = set(chunk_keywords or [])
    hits = [token for token in query_tokens if token in keyword_set]
    hit_ratio = len(hits) / len(query_tokens)

    if chunk_keywords:
        frequency_ratio = sum(
            chunk_keywords.count(token) for token in hits
        ) / max(1, len(chunk_keywords))
    else:
        frequency_ratio = 0.0

    lowered = (content or "").lower()
    literal_bonus = 0.0
    for token in query_tokens:
        if token and token in lowered:
            literal_bonus += 1.0
    literal_bonus = min(1.0, literal_bonus / len(query_tokens))

    return hit_ratio * 0.7 + frequency_ratio * 0.2 + literal_bonus * 0.1
