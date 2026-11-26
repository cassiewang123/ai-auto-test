"""AI 测试用例生成：测试点拆解、用例草稿生成与评审.

对应文档「三、AI 测试用例生成」：

- 快速生成：需求文档 + 知识库 + 用户补充描述，一次性产出用例；
- 分步生成：先把用例设计拆成多个阶段，AI 结合需求与知识库分析后，先向
  测试人员提出缺失信息的问题，再整理出「测试点」供人工确认，确认后才生成
  具体用例（前置条件、操作步骤、预期结果）。

先产出测试点而非直接产出上百条用例，是为了降低人工审核成本：测试人员只需
检查场景是否遗漏、重复或不合理，发现问题可直接修改或删除。

未启用 LLM 时由规则引擎产出可用草稿，保证离线可运行。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client

ENGINE_RULE = "rule"
ENGINE_LLM = "llm"

# 用例产出形态：人工执行（步骤型）/ 接口自动化（请求+断言型）
MODE_MANUAL = "manual"
MODE_API = "api"
VALID_OUTPUT_MODES = {MODE_MANUAL, MODE_API}

# 评审维度：勾选维度并设置权重（1-5，越高越优先）
DEFAULT_REVIEW_DIMENSIONS: dict[str, int] = {
    "覆盖完整性": 3,
    "正确性": 3,
    "冗余去重": 3,
    "边界与异常": 3,
    "步骤清晰度": 3,
    "优先级合理性": 3,
    "前置/数据完整性": 3,
    "需求追溯": 3,
}

# 测试点分类
CATEGORY_FUNCTION = "功能"
CATEGORY_EXCEPTION = "异常"
CATEGORY_BOUNDARY = "边界"
CATEGORY_PERMISSION = "权限"
CATEGORY_SECURITY = "安全"

# 每条功能点按分类展开的模板：文档中「106 条测试点」正是这种多维度铺开
_POINT_TEMPLATES: list[tuple[str, str, str]] = [
    ("功能", "已{subject}时系统按预期完成处理并返回成功结果", "P0"),
    ("异常", "{subject}失败时给出明确错误提示且不泄露敏感信息", "P1"),
    ("边界", "{subject}的输入长度与字符集边界值校验符合约定", "P1"),
    ("边界", "{subject}为空或缺失必填项时阻断提交并提示", "P1"),
    ("权限", "无权限用户{subject}时被拒绝并返回明确状态码", "P1"),
]

_MAX_POINTS = 200
_MAX_CASES_PER_POINT = 1


@dataclass
class TestPointDraft:
    """待确认测试点草稿."""

    module: str
    point: str
    category: str
    priority: str
    trace_source: str | None = None


@dataclass
class CaseDraft:
    """用例草稿.

    ``test_data`` 与 ``api_*`` 是为「可执行」补充的字段：
    - 人工执行形态用 ``test_data`` 列出具体输入值；
    - 接口自动化形态用 ``api_*`` 描述可被执行引擎直接跑的请求与断言。
    两种形态按会话的 ``output_mode`` 二选一填充，另一个留空。
    """

    title: str
    module: str
    category: str
    priority: str
    preconditions: str = ""
    steps: list[str] = field(default_factory=list)
    expected: str = ""
    trace_source: str | None = None
    point_title: str = ""
    # 测试数据：[{"field": "分单号", "value": "ABC123", "note": "已存在"}]
    test_data: list[dict[str, Any]] = field(default_factory=list)
    # 接口自动化字段
    request_method: str | None = None
    request_url: str | None = None
    request_headers: dict[str, Any] = field(default_factory=dict)
    request_body: Any = None
    assertions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def executable(self) -> bool:
        """是否可被接口执行引擎直接执行."""
        return bool(self.request_method and self.request_url)


def _sentences(text: str) -> list[str]:
    parts = [p.strip(" \t-*#>") for p in re.split(r"(?<=[。！？!?；;\n])", text or "")]
    return [p for p in parts if len(p) >= 4]


def _clean(text: str, max_length: int = 80) -> str:
    return re.sub(r"\s+", " ", text or "").strip(" ，。；;、")[:max_length]


# 大模型不一定会严格照搬枚举值：常见「功能测试」「功能性」「功能用例」等变体，
# 优先级也常回「高/中/低」。这里统一收敛到系统约定的取值，避免下游筛选、
# 配色与统计因脏值失效。
_CATEGORY_ALIASES: dict[str, str] = {
    "功能": CATEGORY_FUNCTION,
    "功能测试": CATEGORY_FUNCTION,
    "功能性": CATEGORY_FUNCTION,
    "正常": CATEGORY_FUNCTION,
    "正向": CATEGORY_FUNCTION,
    "异常": CATEGORY_EXCEPTION,
    "异常测试": CATEGORY_EXCEPTION,
    "负向": CATEGORY_EXCEPTION,
    "错误": CATEGORY_EXCEPTION,
    "边界": CATEGORY_BOUNDARY,
    "边界值": CATEGORY_BOUNDARY,
    "边界测试": CATEGORY_BOUNDARY,
    "权限": CATEGORY_PERMISSION,
    "权限测试": CATEGORY_PERMISSION,
    "鉴权": CATEGORY_PERMISSION,
    "安全": CATEGORY_SECURITY,
    "安全测试": CATEGORY_SECURITY,
}

_PRIORITY_ALIASES: dict[str, str] = {
    "p0": "P0", "最高": "P0", "最高优先级": "P0", "紧急": "P0", "critical": "P0",
    "blocker": "P0", "高": "P1", "高优先级": "P1", "重要": "P1", "high": "P1",
    "p1": "P1",
    "中": "P2", "中等": "P2", "一般": "P2", "medium": "P2", "normal": "P2",
    "p2": "P2",
    "低": "P3", "低优先级": "P3", "次要": "P3", "low": "P3", "minor": "P3",
    "p3": "P3",
}


def normalize_category(value: Any) -> str:
    """把模型给的各种分类写法收敛到 功能/异常/边界/权限/安全."""
    text = str(value or "").strip()
    if not text:
        return CATEGORY_FUNCTION
    # 精确匹配优先，其次做包含匹配（如「功能测试类」）
    if text in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[text]
    lowered = text.lower()
    for alias, canonical in _CATEGORY_ALIASES.items():
        if alias.lower() in lowered:
            return canonical
    return CATEGORY_FUNCTION


def normalize_priority(value: Any, default: str = "P1") -> str:
    """把「高/中/低」「High」等写法收敛到 P0-P3."""
    text = str(value or "").strip()
    if not text:
        return default
    if text.upper() in {"P0", "P1", "P2", "P3"}:
        return text.upper()
    lowered = text.lower()
    if lowered in _PRIORITY_ALIASES:
        return _PRIORITY_ALIASES[lowered]
    for alias, canonical in _PRIORITY_ALIASES.items():
        if alias in lowered:
            return canonical
    return default


def build_questions(
    title: str,
    requirement_text: str,
    function_items: list[dict[str, Any]] | None = None,
    clarifications: list[dict[str, Any]] | None = None,
) -> list[str]:
    """分步生成第一步：向测试人员提出缺失信息的问题.

    优先复用需求分析得到的待澄清项；没有分析结果时按通用维度追问。
    """
    questions: list[str] = []
    for item in clarifications or []:
        question = (item or {}).get("question")
        if question:
            questions.append(str(question))

    if not questions:
        joined = (requirement_text or "").lower()
        if not any(token in joined for token in ("长度", "字符", "校验", "唯一")):
            questions.append("用户名与密码/关键字段的具体校验规则是什么（长度、字符集、唯一性）？")
        if not any(token in joined for token in ("异常", "失败", "超时", "重试")):
            questions.append("异常场景（失败、超时、并发）期望的表现与提示文案是什么？")
        if not any(token in joined for token in ("权限", "角色", "越权")):
            questions.append("不同角色访问时的权限边界与越权返回码如何约定？")
        if not any(token in joined for token in ("删除", "关联", "级联")):
            questions.append("关联数据在删除或变更时如何处理（置空/级联/禁止删除）？")

    if function_items and len(questions) < 3:
        modules = [item.get("module") for item in function_items if item.get("module")]
        if modules:
            questions.append(
                f"本次是否覆盖全部模块（{'、'.join(modules[:5])}），是否有暂不测试的范围？"
            )

    if not questions:
        questions.append(f"「{title}」本次要覆盖的测试范围边界是什么（含/不含哪些场景）？")
    return questions[:8]


def generate_test_points_by_rules(
    title: str,
    requirement_text: str,
    function_items: list[dict[str, Any]] | None = None,
    descriptions: list[str] | None = None,
    max_points: int = 60,
) -> list[TestPointDraft]:
    """规则引擎：按功能模块 × 场景维度铺开测试点."""
    points: list[TestPointDraft] = []
    seen: set[str] = set()

    def add(draft: TestPointDraft) -> None:
        key = f"{draft.module}|{draft.point}"
        if key in seen:
            return
        seen.add(key)
        points.append(draft)

    items = function_items or []
    if not items:
        # 没有需求分析结果时，用需求正文句子兜底
        items = [
            {
                "module": title or "通用功能",
                "points": [_clean(sentence, 60) for sentence in _sentences(requirement_text)[:8]],
            }
        ]

    for item in items:
        module = _clean(str(item.get("module") or title or "通用功能"), 32)
        raw_points = item.get("points") or []
        if isinstance(raw_points, str):
            raw_points = [raw_points]
        for raw_point in raw_points:
            subject = _clean(str(raw_point), 60)
            if not subject:
                continue
            for category, point_template, priority in _POINT_TEMPLATES:
                point_text = point_template.format(subject=subject)
                add(
                    TestPointDraft(
                        module=module,
                        point=point_text,
                        category=category,
                        priority=priority,
                        trace_source=subject,
                    )
                )
                if len(points) >= max_points:
                    return points

    for description in descriptions or []:
        subject = _clean(str(description), 60)
        if not subject:
            continue
        add(
            TestPointDraft(
                module="界面交互",
                point=f"页面交互验证：{subject}",
                category=CATEGORY_FUNCTION,
                priority="P2",
                trace_source=subject,
            )
        )
        if len(points) >= max_points:
            return points

    if not points:
        add(
            TestPointDraft(
                module=title or "通用功能",
                point=f"「{title}」核心流程可用性验证",
                category=CATEGORY_FUNCTION,
                priority="P0",
                trace_source=title,
            )
        )
    return points


def _parse_json_payload(content: str) -> Any | None:
    """从模型回复中解析 JSON.

    推理类模型常把 JSON 包在 ```json 代码块里，或在数组前后加一句解释。
    这里依次尝试：整体解析 -> 去代码块 -> 截取首个完整 [...] / {...}。

    注意：被 max_tokens 截断的回复不能退而求其次地解析出内部的半截对象，
    否则会把残缺结果当成有效数据（数量少一半却无人察觉）。因此只在能取到
    **完整**括号片段时才采用截取结果。
    """
    text = (content or "").strip()
    if not text:
        return None

    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    for candidate in (text, _first_json_slice(text)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _first_json_slice(text: str) -> str | None:
    """截出第一个**完整**的 JSON 数组或对象（跳过前后的解释性文字）.

    括号未闭合（模型输出被截断）时返回 None —— 宁可让上层判定失败并回落到
    规则引擎，也不能把残缺数据当作有效结果。

    类型选择有讲究：先出现的括号类型决定期望的片段形态。若文本以 ``[`` 开头，
    就只接受完整的数组；不能因为数组没闭合就退而取内部第一个对象，那会把
    「列表被截断」误判成「只有一条数据」。
    """
    first_array = text.find("[")
    first_object = text.find("{")
    if first_array < 0 and first_object < 0:
        return None

    if first_array >= 0 and (first_object < 0 or first_array < first_object):
        shape = ("[", "]")
    else:
        shape = ("{", "}")

    return _balanced_slice(text, *shape)


def _balanced_slice(text: str, opener: str, closer: str) -> str | None:
    """从第一个 opener 起截出括号配对的完整片段；未闭合返回 None."""
    start = text.find(opener)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None
    return None


def generate_test_points(
    title: str,
    requirement_text: str,
    function_items: list[dict[str, Any]] | None = None,
    descriptions: list[str] | None = None,
    knowledge_context: str = "",
    ai_service: Any | None = None,
    max_points: int = 60,
    prototype_images: list[str] | None = None,
) -> tuple[list[TestPointDraft], str]:
    """生成测试点，返回 ``(测试点列表, 引擎标识)``.

    ``ai_service`` 参数保留为可注入依赖（测试用），实际调用走 LLMClient。
    ``prototype_images`` 是页面原型图的 data URL 列表，会以多模态方式
    随提示词一起发送，让模型看到真实页面而不是只读文字。
    """
    client: LLMClient = ai_service or get_llm_client()
    if not client.enabled():
        return (
            generate_test_points_by_rules(
                title, requirement_text, function_items, descriptions, max_points
            ),
            ENGINE_RULE,
        )

    prompt = build_points_prompt(title, requirement_text, function_items, knowledge_context)
    content = client.complete_with_images(prompt, prototype_images)
    payload = _parse_json_payload(content or "")

    if not isinstance(payload, list) or not payload:
        return (
            generate_test_points_by_rules(
                title, requirement_text, function_items, descriptions, max_points
            ),
            ENGINE_RULE,
        )

    points: list[TestPointDraft] = []
    for entry in payload[:max_points]:
        if not isinstance(entry, dict):
            continue
        point_text = str(entry.get("point") or "").strip()
        if not point_text:
            continue
        points.append(
            TestPointDraft(
                module=str(entry.get("module") or title or "通用功能")[:32],
                point=point_text[:256],
                category=normalize_category(entry.get("category")),
                priority=normalize_priority(entry.get("priority")),
                trace_source=str(entry.get("trace_source") or "")[:256] or None,
            )
        )
    if not points:
        return (
            generate_test_points_by_rules(
                title, requirement_text, function_items, descriptions, max_points
            ),
            ENGINE_RULE,
        )
    return points, ENGINE_LLM


def build_points_prompt(
    title: str,
    requirement_text: str,
    function_items: list[dict[str, Any]] | None = None,
    knowledge_context: str = "",
    has_prototype: bool = False,
) -> str:
    """组装测试点拆解 Prompt.

    这里刻意用强约束压制「模板套话」：明确要求引用需求原文、给出具体
    字段与取值，并禁止「系统按预期完成处理」这类无法执行的措辞。
    """
    summary = json.dumps(function_items or [], ensure_ascii=False)[:4000]
    prototype_hint = (
        "\n本次附带了页面原型截图，请据此补充**界面上真实存在的**字段、"
        "控件、按钮、提示文案与交互约束（哪些字段必填、按钮在什么状态下可用）。\n"
        if has_prototype
        else ""
    )
    prompt = (
        "你是资深测试工程师，正在为一条真实业务需求设计测试点。\n"
        "目标：产出**可被执行者直接照做**的测试点，而不是空泛的场景描述。\n\n"
        "【硬性要求】\n"
        "1. 必须逐条对应需求原文：每条测试点都要引用需求里的具体句子/规则，"
        "写进 trace_source 字段。\n"
        "2. 必须落到具体字段与取值：例如「分单号」而非「某字段」，"
        "「已存在的分单号 XJ2024001」而非「重复数据」。\n"
        "3. 禁止使用这些套话作为测试点主体："
        "「按预期完成处理」「符合约定」「给出明确错误提示」「不泄露敏感信息」"
        "「边界值校验」——如果确实要测，必须写清测的是哪个字段、什么数值、"
        "期望什么具体提示文案或状态。\n"
        "4. 需求里明确写了规则的（如「只有暂存状态可删除」「必填项缺失时提示："
        "必填项缺失，导入不成功」），要原样引用它的条件与文案。\n"
        "5. 一条测试点只测一件事；不要把正常/异常/边界混在一条里。\n"
        "6. 需求中没写、需要猜测的内容，不要编造；这类点放进 clarifications 之外的"
        "字段不要臆造，宁可少写。\n\n"
        "返回 JSON 数组，不要包含解释文字。每个元素字段：\n"
        '- module: 所属模块（用需求里的功能名）\n'
        '- point: 测试点（一句话，含具体字段与条件，可直接照做）\n'
        '- category: 功能/异常/边界/权限/安全\n'
        '- priority: P0/P1/P2/P3\n'
        '- trace_source: 需求原文中对应的那句话（原样摘录）\n\n'
        f"需求标题：{title}\n"
        f"功能清单（来自需求分析，可参考但以原文为准）：{summary}\n"
        f"需求正文：\n{(requirement_text or '')[:8000]}\n"
        f"{prototype_hint}"
    )
    if knowledge_context:
        prompt += f"\n{knowledge_context}\n"
    return prompt


def generate_cases_by_rules(
    points: list[TestPointDraft],
    requirement_title: str,
    max_cases: int = 200,
) -> list[CaseDraft]:
    """规则引擎：把测试点展开为带前置条件、步骤与预期结果的用例草稿."""
    cases: list[CaseDraft] = []
    seen: set[str] = set()

    for index, point in enumerate(points):
        for variant in range(_MAX_CASES_PER_POINT):
            title = point.point if variant == 0 else f"{point.point}（复核）"
            if title in seen:
                continue
            seen.add(title)
            cases.append(
                _case_from_point(point, requirement_title, index)
            )
            if len(cases) >= max_cases:
                return cases
    return cases


def _case_from_point(
    point: TestPointDraft, requirement_title: str, index: int
) -> CaseDraft:
    """按测试点分类生成不同形态的步骤."""
    subject = point.trace_source or point.point
    if point.category == CATEGORY_EXCEPTION:
        steps = [
            "准备满足前置条件的测试数据",
            f"构造异常输入触发「{subject}」失败路径",
            "提交请求并观察系统响应",
            "检查错误提示、日志与数据状态",
        ]
        expected = "系统给出明确且不泄露敏感信息的错误提示，数据保持一致，不产生脏数据"
    elif point.category == CATEGORY_BOUNDARY:
        steps = [
            "准备最小长度、最大长度、空值与特殊字符四组边界数据",
            f"逐组输入并触发「{subject}」",
            "记录每组数据的系统响应",
        ]
        expected = "边界内数据通过校验，越界与空值被明确拦截并给出提示"
    elif point.category == CATEGORY_PERMISSION:
        steps = [
            "分别准备有权限与无权限两类账号",
            f"使用无权限账号尝试「{subject}」",
            "使用有权限账号执行相同操作作为对照",
        ]
        expected = "无权限操作被拒绝并返回约定的状态码，有权限操作正常完成"
    elif point.category == CATEGORY_SECURITY:
        steps = [
            "构造越权/注入类恶意输入",
            f"对「{subject}」发起请求",
            "检查响应与日志",
        ]
        expected = "恶意输入被安全拦截，未泄露敏感数据，未产生越权操作"
    else:
        steps = [
            "准备符合前置条件的测试数据",
            f"执行「{subject}」的核心操作流程",
            "校验返回结果与数据落库情况",
        ]
        expected = "核心流程按需求预期完成，返回成功结果且数据持久化正确"

    return CaseDraft(
        title=point.point[:256],
        module=point.module,
        category=point.category,
        priority=point.priority,
        preconditions=f"已完成「{requirement_title}」相关环境与账号准备",
        steps=steps,
        expected=expected,
        trace_source=point.trace_source,
        point_title=point.point,
    )


def generate_cases(
    points: list[TestPointDraft],
    requirement_title: str,
    requirement_text: str = "",
    knowledge_context: str = "",
    ai_service: Any | None = None,
    max_cases: int = 200,
    output_mode: str = MODE_MANUAL,
    prototype_images: list[str] | None = None,
) -> tuple[list[CaseDraft], str]:
    """为已确认的测试点生成用例草稿，返回 ``(用例列表, 引擎标识)``.

    ``output_mode`` 决定产出形态：
    - ``manual``：前置条件/操作步骤/预期结果 + 具体测试数据，供人工执行；
    - ``api``：额外给出 method/url/请求体/断言，可导入接口库自动执行。
    """
    if not points:
        return [], ENGINE_RULE
    if output_mode not in VALID_OUTPUT_MODES:
        output_mode = MODE_MANUAL

    client: LLMClient = ai_service or get_llm_client()
    if not client.enabled():
        return (
            generate_cases_by_rules(points, requirement_title, max_cases),
            ENGINE_RULE,
        )

    prompt = build_cases_prompt(
        points,
        requirement_title,
        requirement_text,
        knowledge_context,
        output_mode=output_mode,
        has_prototype=bool(prototype_images),
    )
    content = client.complete_with_images(prompt, prototype_images)
    payload = _parse_json_payload(content or "")

    if not isinstance(payload, list) or not payload:
        return generate_cases_by_rules(points, requirement_title, max_cases), ENGINE_RULE

    cases: list[CaseDraft] = []
    for entry in payload[:max_cases]:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        if not title:
            continue
        steps = entry.get("steps") or []
        if isinstance(steps, str):
            steps = [steps]
        cases.append(
            CaseDraft(
                title=title[:256],
                module=str(entry.get("module") or "通用功能")[:128],
                category=normalize_category(entry.get("category")),
                priority=normalize_priority(entry.get("priority")),
                preconditions=str(entry.get("preconditions") or ""),
                steps=[str(step) for step in steps][:20],
                expected=str(entry.get("expected") or ""),
                trace_source=str(entry.get("trace_source") or "")[:256] or None,
                point_title=str(entry.get("point_title") or title)[:256],
                test_data=_normalize_test_data(entry.get("test_data")),
                request_method=_normalize_method(entry.get("request_method")),
                request_url=_normalize_url(entry.get("request_url")),
                request_headers=_normalize_dict(entry.get("request_headers")),
                request_body=entry.get("request_body"),
                assertions=_normalize_assertions(entry.get("assertions")),
            )
        )
    if not cases:
        return generate_cases_by_rules(points, requirement_title, max_cases), ENGINE_RULE
    return cases, ENGINE_LLM


def _normalize_test_data(raw: Any) -> list[dict[str, Any]]:
    """把模型返回的测试数据统一成 ``[{field, value, note}]``.

    模型可能返回字典 ``{"字段": "值"}``、也可能是列表，这里都收敛成
    列表形态，方便前端表格展示与落库。
    """
    items: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for field_name, value in raw.items():
            items.append(
                {
                    "field": str(field_name)[:128],
                    "value": "" if value is None else str(value)[:512],
                    "note": "",
                }
            )
        return items[:50]
    if isinstance(raw, list):
        for entry in raw[:50]:
            if isinstance(entry, dict):
                field_name = entry.get("field") or entry.get("name")
                if not field_name:
                    continue
                value = entry.get("value")
                items.append(
                    {
                        "field": str(field_name)[:128],
                        "value": "" if value is None else str(value)[:512],
                        "note": str(entry.get("note") or "")[:256],
                    }
                )
            elif isinstance(entry, str) and entry.strip():
                items.append(
                    {"field": entry.strip()[:128], "value": "", "note": ""}
                )
    return items


def _normalize_method(value: Any) -> str | None:
    if not value:
        return None
    method = str(value).strip().upper()
    return method[:16] if method else None


def _normalize_url(value: Any) -> str | None:
    if not value:
        return None
    url = str(value).strip()
    return url[:2048] if url else None


def _normalize_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_assertions(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)][:50]


def build_cases_prompt(
    points: list[TestPointDraft],
    requirement_title: str,
    requirement_text: str = "",
    knowledge_context: str = "",
    output_mode: str = MODE_MANUAL,
    has_prototype: bool = False,
) -> str:
    """组装用例生成 Prompt（仅针对已确认的测试点）.

    两种形态共用同一批测试点，只是要求模型补充的字段不同：
    ``manual`` 着重「照着点得下去」的步骤与具体数据；
    ``api`` 额外要求给出可被引擎执行的请求与断言。
    """
    point_lines = "\n".join(
        f"- [{point.module}][{point.category}][{point.priority}] {point.point}"
        f"（来源：{point.trace_source or '未标注'}）"
        for point in points[:200]
    )
    prototype_hint = (
        "\n本次附带了页面原型截图，请让操作步骤中的字段名、按钮文案、"
        "提示语与截图中完全一致。\n"
        if has_prototype
        else ""
    )

    if output_mode == MODE_API:
        shape_rules = (
            "本次要求产出【接口自动化用例】，必须给出可被测试引擎直接执行的请求定义：\n"
            "- request_method: GET/POST/PUT/PATCH/DELETE\n"
            "- request_url: 相对路径或完整 URL（需求没写就按业务语义给合理路径，"
            "并在 description 里标注「URL 需按实际接口确认」）\n"
            "- request_headers: 对象，如 {\"Content-Type\": \"application/json\"}\n"
            "- request_body: 对象或数组，**必须是该用例真实要发的报文**，"
            "字段名取自需求/原型，取值用下面 test_data 里的具体值\n"
            "- assertions: 数组，每项 {\"type\": \"status_code|json_path|business_status\","
            " \"expression\": \"$.xxx\", \"operator\": \"eq\", \"expected\": ...}，"
            "失败场景要断言具体的错误码/错误文案\n"
        )
    else:
        shape_rules = (
            "本次要求产出【人工执行用例】：\n"
            "- steps: 操作步骤数组，每步一个动作，写到「在哪个界面、点什么、填什么」"
            "这个粒度，禁止写「执行核心流程」这类空话\n"
            "- expected: 预期结果，要写清界面反馈、数据变化、提示文案\n"
        )

    prompt = (
        "你是资深测试工程师。请为下面已确认的测试点生成**具体、可执行**的测试用例。\n"
        "返回 JSON 数组，不要包含解释文字。\n\n"
        "【硬性要求】\n"
        "1. 用例标题必须包含具体被测对象与条件，例如"
        "「分单号 XJ2024001 已存在时暂存导入被拒绝并提示」，"
        "禁止写成「按预期完成处理」「符合约定」这类无法判断对错的标题。\n"
        "2. 预期结果必须写具体：具体提示文案、具体状态码或字段值。\n"
        "3. test_data 必须给出本用例实际使用的字段与取值："
        "数组，每项 {\"field\": \"字段名\", \"value\": \"具体值\", "
        "\"note\": \"该值的构造意图，如「已存在的分单号」\"}。"
        "不要把值写成「某个值」「测试数据」这种占位。\n"
        "4. 一条用例只验证一个判定点；不同输入条件拆成多条。\n"
        "5. trace_source 原样摘录需求中对应的那句话，便于追溯。\n\n"
        "每个元素的字段：\n"
        '- title, module, category(功能/异常/边界/权限/安全), priority(P0-P3)\n'
        '- preconditions: 前置条件（账号/数据/状态，写具体）\n'
        '- steps: 操作步骤数组\n'
        '- expected: 预期结果\n'
        '- test_data: 测试数据数组（见上）\n'
        '- trace_source, point_title\n'
        f"{shape_rules}\n"
        f"需求标题：{requirement_title}\n"
        f"需求正文：\n{(requirement_text or '')[:6000]}\n"
        f"已确认测试点：\n{point_lines}\n"
        f"{prototype_hint}"
    )
    if knowledge_context:
        prompt += f"\n{knowledge_context}\n"
    return prompt


# ---------------------------------------------------------------------------
# 多维度评审
# ---------------------------------------------------------------------------
def review_cases(
    cases: list[dict[str, Any]],
    dimensions: dict[str, int] | None = None,
) -> dict[str, Any]:
    """按勾选的评审维度（含权重）对用例草稿做多维检查.

    纯规则实现，不依赖 LLM：输出每个维度的得分与发现的问题，供页面的
    「多维评审报告」展示。
    """
    dimensions = dimensions or DEFAULT_REVIEW_DIMENSIONS
    total_weight = sum(max(1, int(weight)) for weight in dimensions.values()) or 1

    issues: list[dict[str, Any]] = []
    dimension_scores: dict[str, float] = {}

    # 1. 覆盖完整性：模块与分类的覆盖数量
    modules = {str(case.get("module") or "") for case in cases}
    categories = {str(case.get("category") or "") for case in cases}
    coverage = min(1.0, (len(modules) / 3 + len(categories) / 5) / 2) if cases else 0.0
    dimension_scores["覆盖完整性"] = round(coverage, 3)
    if cases and len(categories) < 2:
        issues.append({"dimension": "覆盖完整性", "level": "warning", "message": "用例集中在单一场景分类，建议补充异常与边界场景"})

    # 2. 正确性：标题、步骤、预期是否齐备
    complete = [
        case
        for case in cases
        if case.get("title") and case.get("steps") and case.get("expected")
    ]
    dimension_scores["正确性"] = round(len(complete) / len(cases), 3) if cases else 0.0
    for case in cases:
        if not case.get("expected"):
            issues.append(
                {
                    "dimension": "正确性",
                    "level": "error",
                    "message": f"用例「{case.get('title', '')}」缺少预期结果",
                }
            )

    # 3. 冗余去重
    titles = [str(case.get("title") or "") for case in cases]
    unique_titles = set(titles)
    dimension_scores["冗余去重"] = (
        round(len(unique_titles) / len(titles), 3) if titles else 0.0
    )
    duplicates = {title for title in titles if titles.count(title) > 1}
    for title in sorted(duplicates):
        issues.append(
            {"dimension": "冗余去重", "level": "warning", "message": f"存在重复用例标题「{title}」"}
        )

    # 4. 边界与异常：分类占比
    boundary_like = {"异常", "边界", "安全", "权限"}
    boundary_count = sum(1 for case in cases if case.get("category") in boundary_like)
    dimension_scores["边界与异常"] = (
        round(boundary_count / len(cases), 3) if cases else 0.0
    )
    if cases and boundary_count == 0:
        issues.append(
            {"dimension": "边界与异常", "level": "warning", "message": "缺少异常、边界或权限类用例"}
        )

    # 5. 步骤清晰度：步骤条数 3-8 视为清晰
    clear_steps = [
        case
        for case in cases
        if isinstance(case.get("steps"), list) and 3 <= len(case.get("steps") or []) <= 8
    ]
    dimension_scores["步骤清晰度"] = (
        round(len(clear_steps) / len(cases), 3) if cases else 0.0
    )

    # 6. 优先级合理性：P0/P1 应占多数
    high_priority = sum(
        1 for case in cases if case.get("priority") in {"P0", "P1"}
    )
    dimension_scores["优先级合理性"] = (
        round(high_priority / len(cases), 3) if cases else 0.0
    )

    # 7. 前置/数据完整性
    with_preconditions = [case for case in cases if case.get("preconditions")]
    dimension_scores["前置/数据完整性"] = (
        round(len(with_preconditions) / len(cases), 3) if cases else 0.0
    )

    # 8. 需求追溯
    with_trace = [case for case in cases if case.get("trace_source")]
    dimension_scores["需求追溯"] = (
        round(len(with_trace) / len(cases), 3) if cases else 0.0
    )

    weighted = 0.0
    for name, weight in dimensions.items():
        weighted += dimension_scores.get(name, 0.0) * max(1, int(weight)) / total_weight

    return {
        "overall_score": round(weighted * 100, 1),
        "dimension_scores": {k: round(v * 100, 1) for k, v in dimension_scores.items()},
        "dimensions": dimensions,
        "issues": issues[:50],
    }
