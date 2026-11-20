"""需求分析服务：结构化输出功能清单 / 界面描述 / 待澄清项.

对应文档「1. 需求分析」。实际项目里需求文档常常描述不充分、业务规则不明确、
异常场景缺失，直接据此写用例容易漏测并返工。本服务把需求正文（含附件文档文本）
交给大模型做结构化分析，输出三部分：

- ``function_items``   功能清单：模块 → 具体功能点
- ``ui_descriptions``  界面描述：页面 → 布局/功能区域/操作入口/交互
- ``clarifications``   待澄清项：描述矛盾、缺失的业务规则、边界未定义

未启用外部 LLM（``LLM_EXTERNAL_ENABLED=false`` 或无 API Key）时，完全由本地
规则引擎产出结果，保证离线可用且数据不外发；分析结果会标注 ``engine``。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.services.ai_service import AIService

ENGINE_RULE = "rule"
ENGINE_LLM = "llm"

# 规则引擎的模块划分依据：需求文档中常见的中文功能域关键词
_MODULE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("登录与认证", ("登录", "注册", "认证", "密码", "验证码", "令牌", "token", "单点登录", "注销", "退出")),
    ("权限与角色", ("权限", "角色", "授权", "鉴权", "管理员", "超管", "审批", "成员")),
    ("项目管理", ("项目", "工作区", "归档", "删除项目")),
    ("需求管理", ("需求", "分析", "澄清", "用例生成", "测试点")),
    ("知识库", ("知识库", "文档", "分块", "检索", "rag", "索引")),
    ("数据管理", ("导入", "导出", "上传", "下载", "数据", "字段", "列表", "查询", "筛选")),
    ("接口与集成", ("接口", "api", "webhook", "回调", "消息", "通知", "第三方", "集成")),
    ("报表与统计", ("报表", "统计", "图表", "看板", "趋势", "覆盖率")),
    ("系统设置", ("配置", "设置", "参数", "开关", "环境变量", "日志", "审计")),
]

_UI_HINTS = (
    "页面", "界面", "弹窗", "对话框", "抽屉", "表单", "按钮", "入口",
    "菜单", "列表页", "详情页", "导航", "布局", "标签页",
)

# 规则引擎用来发现「需求缺口」的信号词
_VAGUE_WORDS = (
    "等", "等等", "类似", "若干", "适当", "合理", "尽量", "尽快", "友好",
    "若干条", "相关", "某些", "部分",
)
_RULE_HINTS = (
    "长度", "字符", "格式", "上限", "下限", "最大", "最小", "必填", "选填",
    "唯一", "校验", "限制", "超时", "有效期", "频率", "次数", "并发",
)
_EXCEPTION_HINTS = ("异常", "失败", "错误", "超时", "重试", "回滚", "中断", "并发", "越权")
_PERMISSION_HINTS = ("权限", "角色", "越权", "未授权", "非成员", "只读", "可见")
_DATA_HINTS = ("删除", "级联", "关联", "置空", "保留", "历史", "版本")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;\n])")


@dataclass
class RequirementAnalysisResult:
    """一次需求分析的结果."""

    engine: str
    function_items: list[dict[str, Any]] = field(default_factory=list)
    ui_descriptions: list[dict[str, Any]] = field(default_factory=list)
    clarifications: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "function_items": self.function_items,
            "ui_descriptions": self.ui_descriptions,
            "clarifications": self.clarifications,
            "markdown": render_markdown(self.function_items, self.ui_descriptions, self.clarifications),
        }


def _sentences(text: str) -> list[str]:
    """把正文拆成句子，过滤过短片段."""
    parts = [p.strip(" \t-*#>") for p in _SENTENCE_SPLIT_RE.split(text or "")]
    return [p for p in parts if len(p) >= 4]


def _clean_point(sentence: str, max_length: int = 120) -> str:
    point = re.sub(r"\s+", " ", sentence).strip(" ，。；;、")
    return point[:max_length]


def _split_modules(title: str, text: str) -> dict[str, list[str]]:
    """按关键词把句子归入功能模块."""
    modules: dict[str, list[str]] = {title or "通用功能": []}
    for sentence in _sentences(text):
        lowered = sentence.lower()
        matched = False
        for module, keywords in _MODULE_RULES:
            if any(keyword in lowered for keyword in keywords):
                modules.setdefault(module, []).append(_clean_point(sentence))
                matched = True
                break
        if not matched:
            modules.setdefault(title or "通用功能", []).append(_clean_point(sentence))

    # 去掉空模块，并限制每模块条目数，避免规则引擎产出过长清单
    return {
        module: points[:12]
        for module, points in modules.items()
        if points
    }


def _extract_ui_descriptions(text: str) -> list[dict[str, str]]:
    """从含界面线索的句子中整理界面描述."""
    descriptions: list[dict[str, str]] = []
    seen: set[str] = set()
    for sentence in _sentences(text):
        lowered = sentence.lower()
        if not any(hint in lowered for hint in _UI_HINTS):
            continue
        # 页面归属：优先「XX页/XX弹窗」这样的显式说法
        page_match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{2,20})(页面|页|弹窗|对话框|抽屉)", sentence)
        page = page_match.group(0) if page_match else "全局交互"
        if page in seen:
            continue
        seen.add(page)
        descriptions.append(
            {
                "page": page,
                "description": _clean_point(sentence, 200),
            }
        )
    return descriptions[:15]


def _extract_clarifications(title: str, text: str) -> list[dict[str, str]]:
    """识别需求中的模糊表述与缺失项，生成待澄清问题."""
    items: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(question: str, reason: str) -> None:
        key = question[:40]
        if key in seen:
            return
        seen.add(key)
        items.append({"question": question, "reason": reason})

    sentences = _sentences(text)

    for sentence in sentences:
        lowered = sentence.lower()
        if any(word in lowered for word in _VAGUE_WORDS):
            add(
                f"「{_clean_point(sentence, 60)}」中的模糊表述具体指什么？",
                "需求使用了模糊描述，无法据此设计可验证的断言",
            )
        if any(hint in lowered for hint in _RULE_HINTS):
            continue

    # 全局缺项扫描：规则/异常/权限/数据一致性四类，缺哪类就提示哪类
    joined = "\n".join(sentences).lower()
    if not any(hint in joined for hint in _RULE_HINTS):
        add(
            f"「{title}」的字段校验规则是什么（长度、字符集、必填、唯一性）？",
            "需求未定义校验规则，边界值用例无法确定预期结果",
        )
    if not any(hint in joined for hint in _EXCEPTION_HINTS):
        add(
            f"「{title}」在异常场景下（超时、失败、并发）期望的表现是什么？",
            "需求缺少异常与失败处理约定，异常场景用例无法落地",
        )
    if not any(hint in joined for hint in _PERMISSION_HINTS):
        add(
            f"「{title}」的访问权限如何控制，非授权用户访问应返回什么？",
            "需求未定义权限边界，越权场景用例缺少判定标准",
        )
    if not any(hint in joined for hint in _DATA_HINTS):
        add(
            f"「{title}」关联数据删除或变更时的处理约定是什么（置空/级联/禁止）？",
            "需求未定义数据关联处理，数据一致性用例缺少依据",
        )
    add(
        f"「{title}」是否需要与知识库中的技术/业务文档保持一致？如有冲突以哪份为准？",
        "提交前确认业务口径，避免测试结论与产品定义不一致",
    )
    return items[:12]


def analyze_by_rules(
    title: str, text: str, knowledge_context: str = ""
) -> RequirementAnalysisResult:
    """规则引擎分析：不依赖 LLM，离线可用的兜底实现."""
    source = text or ""
    if knowledge_context:
        # 知识库上下文参与模块归类，但不进入功能清单正文
        source = f"{source}\n{knowledge_context}"

    modules = _split_modules(title, source)
    function_items = [
        {"module": module, "points": points}
        for module, points in modules.items()
    ][:10]

    return RequirementAnalysisResult(
        engine=ENGINE_RULE,
        function_items=function_items,
        ui_descriptions=_extract_ui_descriptions(text),
        clarifications=_extract_clarifications(title, text),
    )


def _parse_llm_payload(content: str) -> dict[str, Any] | None:
    """从模型输出中提取 JSON，容忍 ```json 包裹."""
    text = (content or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_list(value: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    """把模型返回的列表结果规整为 dict 列表，丢弃无法识别的项."""
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for entry in value:
        if isinstance(entry, dict):
            items.append(entry)
        elif isinstance(entry, str) and entry.strip():
            items.append({keys[0]: entry.strip()})
    return items


def analyze_requirement(
    title: str,
    text: str,
    knowledge_context: str = "",
    ai_service: AIService | None = None,
) -> RequirementAnalysisResult:
    """分析需求：有 LLM 走 LLM，失败或未启用时回退规则引擎."""
    service = ai_service or AIService()
    llm = service._get_llm()  # noqa: SLF001 - 复用既有 LLM 获取与总闸校验
    if llm is None:
        return analyze_by_rules(title, text, knowledge_context)

    prompt = build_analysis_prompt(title, text, knowledge_context)
    try:
        response = llm.invoke(prompt)
        payload = _parse_llm_payload(getattr(response, "content", "") or "")
    except Exception:
        return analyze_by_rules(title, text, knowledge_context)
    if not payload:
        return analyze_by_rules(title, text, knowledge_context)

    function_items = _normalize_list(payload.get("function_items"), ("module",))
    ui_descriptions = _normalize_list(payload.get("ui_descriptions"), ("page",))
    clarifications = _normalize_list(payload.get("clarifications"), ("question",))

    fallback = analyze_by_rules(title, text, knowledge_context)
    # 模型返回空的部分用规则结果补齐，避免界面出现空板块
    return RequirementAnalysisResult(
        engine=ENGINE_LLM,
        function_items=function_items or fallback.function_items,
        ui_descriptions=ui_descriptions or fallback.ui_descriptions,
        clarifications=clarifications or fallback.clarifications,
    )


def build_analysis_prompt(
    title: str, text: str, knowledge_context: str = ""
) -> str:
    """组装需求分析 Prompt，要求模型输出严格 JSON."""
    max_source_chars = 12000
    source = (text or "")[:max_source_chars]
    prompt = (
        "你是资深测试工程师，请对下面的需求文档做结构化分析，"
        "输出严格 JSON，不要包含解释文字。\n\n"
        "JSON 结构：\n"
        "{\n"
        '  "function_items": [{"module": "模块名", "points": ["功能点1", "功能点2"]}],\n'
        '  "ui_descriptions": [{"page": "页面名", "description": "布局/功能区域/操作入口/交互行为"}],\n'
        '  "clarifications": [{"question": "待澄清问题", "reason": "为什么要澄清"}]\n'
        "}\n\n"
        "要求：\n"
        "1. 功能清单需覆盖需求提到的全部功能模块与具体功能点；\n"
        "2. 只对涉及页面交互的需求输出界面描述；\n"
        "3. 待澄清项要指出描述不清晰、前后矛盾或缺少业务规则的地方；\n"
        "4. 全部使用中文。\n\n"
        f"需求标题：{title}\n"
        f"需求正文：\n{source}\n"
    )
    if knowledge_context:
        prompt += f"\n{knowledge_context}\n"
    return prompt


def render_markdown(
    function_items: list[dict[str, Any]],
    ui_descriptions: list[dict[str, Any]],
    clarifications: list[dict[str, Any]],
) -> str:
    """把三部分分析结果渲染为可导出的 Markdown."""
    lines: list[str] = ["## 一、功能清单", ""]
    if not function_items:
        lines.append("_本次分析未识别出功能模块，请补充需求正文后重新分析。_")
    for item in function_items:
        module = item.get("module") or "通用功能"
        lines.append(f"### {module}")
        points = item.get("points") or []
        if isinstance(points, str):
            points = [points]
        for point in points:
            lines.append(f"- {point}")
        lines.append("")

    lines.extend(["## 二、界面描述", ""])
    if not ui_descriptions:
        lines.append("_本次需求未涉及界面交互描述。_")
    for item in ui_descriptions:
        lines.append(f"### {item.get('page') or '全局交互'}")
        description = item.get("description") or ""
        for segment in str(description).splitlines() or [""]:
            if segment.strip():
                lines.append(f"- {segment.strip()}")
        lines.append("")

    lines.extend(["## 三、待澄清项", ""])
    if not clarifications:
        lines.append("_未发现明显待澄清项。_")
    for index, item in enumerate(clarifications, start=1):
        question = item.get("question") or ""
        reason = item.get("reason") or ""
        lines.append(f"{index}. **{question}**")
        if reason:
            lines.append(f"   - 原因：{reason}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"
