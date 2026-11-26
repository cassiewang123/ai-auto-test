"""测试设计服务的提示词约束与模型输出解析.

这些用例不调用真实 LLM：用假的 client 返回固定 JSON，验证
「提示词是否真的在压制模板套话」以及「模型输出能否被正确收敛」。
"""
from __future__ import annotations

from app.services import test_design_service as svc


class FakeClient:
    """可注入的假 LLM 客户端."""

    def __init__(self, payload: str, enabled: bool = True) -> None:
        self.payload = payload
        self._enabled = enabled
        self.prompts: list[str] = []
        self.images: list[list[str]] = []
        # 回退原因诊断会读这两个字段，真实 LLMClient 上有同名属性
        from types import SimpleNamespace

        self.settings = SimpleNamespace(
            LLM_EXTERNAL_ENABLED=enabled, OPENAI_API_KEY="sk-fake" if enabled else ""
        )

    def enabled(self) -> bool:
        return self._enabled

    def complete(self, prompt: str):
        self.prompts.append(prompt)
        return self.payload

    def complete_with_images(self, prompt: str, image_paths=None):
        self.prompts.append(prompt)
        self.images.append(list(image_paths or []))
        return self.payload


# ---------------------------------------------------------------------------
# 提示词约束
# ---------------------------------------------------------------------------
def test_points_prompt_forbids_template_phrases():
    prompt = svc.build_points_prompt("多式联运", "需求正文")
    # 明确列为禁止的套话，必须出现在提示词里
    for phrase in ("按预期完成处理", "符合约定", "不泄露敏感信息"):
        assert phrase in prompt
    assert "trace_source" in prompt
    # 要求引用原文
    assert "原样摘录" in prompt


def test_points_prompt_mentions_prototype_when_present():
    without = svc.build_points_prompt("t", "body", has_prototype=False)
    with_prototype = svc.build_points_prompt("t", "body", has_prototype=True)
    assert "页面原型" not in without
    assert "页面原型" in with_prototype


def test_cases_prompt_manual_mode_requires_concrete_steps():
    prompt = svc.build_cases_prompt(
        [svc.TestPointDraft("m", "p", "功能", "P0")],
        "t",
        "body",
        output_mode=svc.MODE_MANUAL,
    )
    assert "人工执行用例" in prompt
    assert "禁止写「执行核心流程」" in prompt
    assert "test_data" in prompt


def test_cases_prompt_api_mode_requires_request_and_assertions():
    prompt = svc.build_cases_prompt(
        [svc.TestPointDraft("m", "p", "异常", "P0")],
        "t",
        "body",
        output_mode=svc.MODE_API,
    )
    assert "接口自动化用例" in prompt
    for field in ("request_method", "request_url", "request_body", "assertions"):
        assert field in prompt


# ---------------------------------------------------------------------------
# 模型输出解析
# ---------------------------------------------------------------------------
def test_generate_cases_parses_executable_fields():
    payload = """
    [
      {
        "title": "分单号 XJ001 已存在时暂存导入被拒绝",
        "module": "多式联运",
        "category": "异常",
        "priority": "P0",
        "preconditions": "已存在一张分单号 XJ001 的暂存单证",
        "steps": ["进入导入页", "上传含 XJ001 的文件", "点击导入"],
        "expected": "提示：此分单号已存在，单证无法导入",
        "test_data": [{"field": "分单号", "value": "XJ001", "note": "已存在"}],
        "request_method": "post",
        "request_url": "/api/import",
        "request_headers": {"Content-Type": "application/json"},
        "request_body": {"billNo": "XJ001"},
        "assertions": [
          {"type": "status_code", "operator": "eq", "expected": 400}
        ],
        "trace_source": "此分单号已存在，单证无法导入"
      }
    ]
    """
    client = FakeClient(payload)
    cases, engine = svc.generate_cases(
        [svc.TestPointDraft("多式联运", "p", "异常", "P0")],
        "多式联运",
        "body",
        ai_service=client,
        output_mode=svc.MODE_API,
    )

    assert engine == svc.ENGINE_LLM
    assert len(cases) == 1
    case = cases[0]
    assert case.executable is True
    # 方法统一大写
    assert case.request_method == "POST"
    assert case.request_url == "/api/import"
    assert case.request_body == {"billNo": "XJ001"}
    assert case.test_data == [
        {"field": "分单号", "value": "XJ001", "note": "已存在"}
    ]
    assert case.assertions[0]["type"] == "status_code"


def test_generate_cases_marks_manual_case_not_executable():
    payload = """
    [{"title": "人工用例", "steps": ["a"], "expected": "b",
      "test_data": {"字段": "值"}}]
    """
    cases, _ = svc.generate_cases(
        [svc.TestPointDraft("m", "p", "功能", "P0")],
        "t",
        "body",
        ai_service=FakeClient(payload),
        output_mode=svc.MODE_MANUAL,
    )
    case = cases[0]
    assert case.executable is False
    # 字典形态的测试数据被收敛为列表
    assert case.test_data == [{"field": "字段", "value": "值", "note": ""}]


def test_generate_cases_falls_back_to_rules_on_bad_json():
    cases, engine = svc.generate_cases(
        [svc.TestPointDraft("m", "p", "功能", "P0")],
        "t",
        "body",
        ai_service=FakeClient("这不是 JSON"),
    )
    assert engine == svc.ENGINE_RULE
    assert cases


def test_generate_cases_uses_rules_when_llm_disabled():
    cases, engine = svc.generate_cases(
        [svc.TestPointDraft("m", "p", "功能", "P0")],
        "t",
        "body",
        ai_service=FakeClient("[]", enabled=False),
    )
    assert engine == svc.ENGINE_RULE
    assert cases


def test_generate_test_points_passes_prototype_images():
    payload = '[{"module":"m","point":"p","category":"功能","priority":"P0"}]'
    client = FakeClient(payload)
    points, engine = svc.generate_test_points(
        "t", "body", ai_service=client, prototype_images=["data:image/png;base64,AAA"]
    )
    assert engine == svc.ENGINE_LLM
    assert points
    assert client.images[0] == ["data:image/png;base64,AAA"]


def test_normalize_test_data_handles_messy_input():
    assert svc._normalize_test_data(None) == []
    assert svc._normalize_test_data("字符串") == []
    assert svc._normalize_test_data([{"value": "没有字段名"}]) == []
    assert svc._normalize_test_data(["直接字符串"]) == [
        {"field": "直接字符串", "value": "", "note": ""}
    ]
    # 超长取值截断，避免撑爆字段
    long_value = "x" * 1000
    item = svc._normalize_test_data({"f": long_value})[0]
    assert len(item["value"]) <= 512


# ---------------------------------------------------------------------------
# 模型输出容错：推理模型的空输出、脏枚举值、带说明文字的 JSON
# ---------------------------------------------------------------------------
def test_parse_json_payload_handles_fence_with_language():
    assert svc._parse_json_payload('```json\n[{"a": 1}]\n```') == [{"a": 1}]


def test_parse_json_payload_handles_surrounding_prose():
    """模型常在 JSON 前后加一句解释，必须能截出来."""
    text = '好的，以下是测试点：\n[{"a": 1}, {"b": 2}]\n以上共 2 条。'
    assert svc._parse_json_payload(text) == [{"a": 1}, {"b": 2}]


def test_parse_json_payload_handles_object_payload():
    assert svc._parse_json_payload('说明文字 {"a": 1} 结尾') == {"a": 1}


def test_parse_json_payload_ignores_brackets_inside_strings():
    """字符串里的 ] 不能误判为数组结束."""
    text = '[{"point": "导入 [必填] 字段"}]'
    assert svc._parse_json_payload(text) == [{"point": "导入 [必填] 字段"}]


def test_parse_json_payload_returns_none_for_truncated_json():
    """被 max_tokens 截断的 JSON 无法解析，应返回 None 交由上层回落."""
    assert svc._parse_json_payload('[{"a": 1}, {"b":') is None


def test_normalize_category_maps_model_variants():
    assert svc.normalize_category("功能测试") == svc.CATEGORY_FUNCTION
    assert svc.normalize_category("异常场景") == svc.CATEGORY_EXCEPTION
    assert svc.normalize_category("边界值") == svc.CATEGORY_BOUNDARY
    assert svc.normalize_category("权限校验") == svc.CATEGORY_PERMISSION
    assert svc.normalize_category("安全测试") == svc.CATEGORY_SECURITY
    # 未知值收敛为功能，避免脏值进库
    assert svc.normalize_category("随便写的") == svc.CATEGORY_FUNCTION
    assert svc.normalize_category(None) == svc.CATEGORY_FUNCTION


def test_normalize_priority_maps_model_variants():
    assert svc.normalize_priority("高") == "P1"
    assert svc.normalize_priority("High") == "P1"
    assert svc.normalize_priority("最高") == "P0"
    assert svc.normalize_priority("中") == "P2"
    assert svc.normalize_priority("低") == "P3"
    assert svc.normalize_priority("p0") == "P0"
    assert svc.normalize_priority("??") == "P1"
    assert svc.normalize_priority(None) == "P1"


def test_generated_cases_use_normalized_enums():
    """模型返回「功能测试」「高」时，落库值必须是约定的枚举."""
    payload = """[{"title": "用例", "category": "功能测试", "priority": "高",
                   "steps": ["a"], "expected": "b"}]"""
    cases, engine = svc.generate_cases(
        [svc.TestPointDraft("m", "p", "功能", "P0")],
        "t", "body", ai_service=FakeClient(payload),
    )
    assert engine == svc.ENGINE_LLM
    assert cases[0].category == svc.CATEGORY_FUNCTION
    assert cases[0].priority == "P1"


def test_generated_points_use_normalized_enums():
    payload = """[{"module": "m", "point": "p", "category": "边界值",
                   "priority": "最高"}]"""
    points, engine = svc.generate_test_points(
        "t", "body", ai_service=FakeClient(payload),
    )
    assert engine == svc.ENGINE_LLM
    assert points[0].category == svc.CATEGORY_BOUNDARY
    assert points[0].priority == "P0"


# ---------------------------------------------------------------------------
# 规则引擎兜底：带上真实字段名，并明确标注待补充
# ---------------------------------------------------------------------------
def test_rule_fallback_extracts_field_names_from_requirement():
    """规则引擎应从需求原文提取带引号的字段名，而不是写「某字段」."""
    point = svc.TestPointDraft(
        module="进口食品申报",
        point='商品表体"生产日期"留空时提交应拦截',
        category="异常",
        priority="P0",
        trace_source='商品表体"生产日期"不可为空',
    )
    cases = svc.generate_cases_by_rules([point], "信天翁1125")
    case = cases[0]

    assert any("生产日期" in step for step in case.steps)
    # 测试数据不再是空数组，而是带字段名的待补充项
    assert case.test_data
    assert case.test_data[0]["field"] == "生产日期"


def test_rule_fallback_marks_placeholders_explicitly():
    """兜底用例必须明确标注待补充，避免被当成最终用例误用."""
    point = svc.TestPointDraft("m", "某个没有引号字段的测试点", "功能", "P0")
    cases = svc.generate_cases_by_rules([point], "需求")
    case = cases[0]

    assert "【规则引擎生成】" in case.preconditions
    assert any("【待补充】" in step for step in case.steps)
    assert case.test_data[0]["note"].startswith("【待补充】")


def test_extract_quoted_terms_handles_multiple_quote_styles():
    text = '单证"分单号"为空时提示「必填项缺失，导入不成功」，参见『导入规范』'
    terms = svc._extract_quoted_terms(text)
    assert "分单号" in terms
    assert "必填项缺失，导入不成功" in terms
    assert "导入规范" in terms


def test_extract_quoted_terms_returns_empty_without_quotes():
    assert svc._extract_quoted_terms("没有任何引号的普通句子") == []
    assert svc._extract_quoted_terms(None) == []


# ---------------------------------------------------------------------------
# 分批生成：单次输出被截断时不应整批作废
# ---------------------------------------------------------------------------
class _StubClient:
    """按调用次数返回不同结果的假客户端."""

    def __init__(self, responses: list[str]) -> None:
        from types import SimpleNamespace

        self.responses = responses
        self.calls = 0
        self.settings = SimpleNamespace(
            LLM_EXTERNAL_ENABLED=True, OPENAI_API_KEY="sk-fake"
        )

    def enabled(self) -> bool:
        return True

    def complete(self, prompt: str):
        return self._next()

    def complete_with_images(self, prompt: str, image_paths=None):
        return self._next()

    def _next(self):
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[index]


def test_points_batch_fallback_recovers_from_truncation():
    """首轮返回被截断的 JSON 时，应改用分批继续生成而不是回退规则引擎."""
    truncated = '[{"module": "m", "point": "被截断的点"'  # 故意不闭合
    batch_ok = '[{"module":"m","point":"分批点 A","category":"功能","priority":"P0"}]'

    client = _StubClient([truncated, batch_ok])
    points, engine = svc.generate_test_points(
        "需求", "需求正文", ai_service=client, max_points=3
    )

    assert engine == svc.ENGINE_LLM
    assert points
    # 分批确实发生了：首轮之外还有后续调用
    assert client.calls > 1


def test_points_batch_returns_none_when_all_fail():
    client = _StubClient(["不是 JSON"])
    points, engine = svc.generate_test_points(
        "需求", "需求正文", ai_service=client, max_points=3
    )
    assert engine == svc.ENGINE_RULE
    assert points


def test_cases_batch_fallback_recovers_from_truncation():
    truncated = '[{"title": "被截断"'
    batch_ok = (
        '[{"title":"分批用例","steps":["a"],"expected":"b",'
        '"test_data":[{"field":"F","value":"V"}]}]'
    )
    client = _StubClient([truncated, batch_ok])

    cases, engine = svc.generate_cases(
        [svc.TestPointDraft("m", "p", "功能", "P0")],
        "需求",
        "需求正文",
        ai_service=client,
    )
    assert engine == svc.ENGINE_LLM
    assert cases
    assert cases[0].test_data


def test_cases_batch_deduplicates_titles():
    same = (
        '[{"title":"同一条","steps":["a"],"expected":"b"}]'
    )
    client = _StubClient(['broken', same])
    cases, engine = svc.generate_cases(
        [svc.TestPointDraft("m", "p1", "功能", "P0"),
         svc.TestPointDraft("m", "p2", "功能", "P0")],
        "需求",
        "正文",
        ai_service=client,
    )
    assert engine == svc.ENGINE_LLM
    titles = [c.title for c in cases]
    assert len(titles) == len(set(titles))
