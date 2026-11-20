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

from app.services.ai_service import AIService

ENGINE_RULE = "rule"
ENGINE_LLM = "llm"

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
    """用例草稿."""

    title: str
    module: str
    category: str
    priority: str
    preconditions: str = ""
    steps: list[str] = field(default_factory=list)
    expected: str = ""
    trace_source: str | None = None
    point_title: str = ""


def _sentences(text: str) -> list[str]:
    parts = [p.strip(" \t-*#>") for p in re.split(r"(?<=[。！？!?；;\n])", text or "")]
    return [p for p in parts if len(p) >= 4]


def _clean(text: str, max_length: int = 80) -> str:
    return re.sub(r"\s+", " ", text or "").strip(" ，。；;、")[:max_length]


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
    text = (content or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def generate_test_points(
    title: str,
    requirement_text: str,
    function_items: list[dict[str, Any]] | None = None,
    descriptions: list[str] | None = None,
    knowledge_context: str = "",
    ai_service: AIService | None = None,
    max_points: int = 60,
) -> tuple[list[TestPointDraft], str]:
    """生成测试点，返回 ``(测试点列表, 引擎标识)``."""
    service = ai_service or AIService()
    llm = service._get_llm()  # noqa: SLF001
    if llm is None:
        return (
            generate_test_points_by_rules(
                title, requirement_text, function_items, descriptions, max_points
            ),
            ENGINE_RULE,
        )

    prompt = build_points_prompt(title, requirement_text, function_items, knowledge_context)
    try:
        response = llm.invoke(prompt)
        payload = _parse_json_payload(getattr(response, "content", "") or "")
    except Exception:
        payload = None

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
                category=str(entry.get("category") or CATEGORY_FUNCTION)[:16],
                priority=str(entry.get("priority") or "P1")[:8],
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
) -> str:
    """组装测试点拆解 Prompt."""
    summary = json.dumps(function_items or [], ensure_ascii=False)[:4000]
    prompt = (
        "你是资深测试工程师。请结合需求与知识库内容，拆解出可执行的测试点，"
        "返回 JSON 数组，不要包含解释文字。\n\n"
        "每个元素的字段：\n"
        '- module: 所属模块\n'
        '- point: 测试点描述（一句话，可验证）\n'
        '- category: 功能/异常/边界/权限/安全\n'
        '- priority: P0/P1/P2/P3\n'
        '- trace_source: 该测试点来自需求中的哪句话\n\n'
        f"需求标题：{title}\n"
        f"功能清单：{summary}\n"
        f"需求正文：\n{(requirement_text or '')[:8000]}\n"
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
    ai_service: AIService | None = None,
    max_cases: int = 200,
) -> tuple[list[CaseDraft], str]:
    """为已确认的测试点生成用例草稿，返回 ``(用例列表, 引擎标识)``."""
    if not points:
        return [], ENGINE_RULE

    service = ai_service or AIService()
    llm = service._get_llm()  # noqa: SLF001
    if llm is None:
        return generate_cases_by_rules(points, requirement_title, max_cases), ENGINE_RULE

    prompt = build_cases_prompt(points, requirement_title, requirement_text, knowledge_context)
    try:
        response = llm.invoke(prompt)
        payload = _parse_json_payload(getattr(response, "content", "") or "")
    except Exception:
        payload = None

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
                category=str(entry.get("category") or CATEGORY_FUNCTION)[:16],
                priority=str(entry.get("priority") or "P1")[:8],
                preconditions=str(entry.get("preconditions") or ""),
                steps=[str(step) for step in steps][:20],
                expected=str(entry.get("expected") or ""),
                trace_source=str(entry.get("trace_source") or "")[:256] or None,
                point_title=str(entry.get("point_title") or title)[:256],
            )
        )
    if not cases:
        return generate_cases_by_rules(points, requirement_title, max_cases), ENGINE_RULE
    return cases, ENGINE_LLM


def build_cases_prompt(
    points: list[TestPointDraft],
    requirement_title: str,
    requirement_text: str = "",
    knowledge_context: str = "",
) -> str:
    """组装用例生成 Prompt（仅针对已确认的测试点）."""
    point_lines = "\n".join(
        f"- [{point.module}][{point.category}][{point.priority}] {point.point}"
        for point in points[:200]
    )
    prompt = (
        "你是资深测试工程师。请为下面已确认的测试点生成具体测试用例，"
        "返回 JSON 数组，不要包含解释文字。\n\n"
        "每个元素的字段：\n"
        '- title: 用例标题\n'
        '- module: 所属模块\n'
        '- category: 功能/异常/边界/权限/安全\n'
        '- priority: P0/P1/P2/P3\n'
        '- preconditions: 前置条件\n'
        '- steps: 操作步骤数组\n'
        '- expected: 预期结果\n'
        '- trace_source: 需求追溯来源\n'
        "- point_title: 对应的测试点\n\n"
        f"需求标题：{requirement_title}\n"
        f"需求正文：\n{(requirement_text or '')[:6000]}\n"
        f"已确认测试点：\n{point_lines}\n"
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
