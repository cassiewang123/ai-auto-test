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
