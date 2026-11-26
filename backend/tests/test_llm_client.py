"""LLM 客户端的可用性判断与图片编码测试.

重点覆盖「默认不外发」与「图片附件构造」两条不能出错的路径，
不发起任何真实网络请求。
"""
from __future__ import annotations

import base64

import pytest

from app.config import get_settings
from app.services import llm_client as llm_module
from app.services.llm_client import LLMClient, image_mime_type


@pytest.fixture(autouse=True)
def _clear_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _configure(monkeypatch, *, enabled: bool, api_key: str = "") -> None:
    monkeypatch.setenv("LLM_EXTERNAL_ENABLED", str(enabled).lower())
    monkeypatch.setenv("OPENAI_API_KEY", api_key)
    get_settings.cache_clear()


def test_disabled_by_gate_even_with_key(monkeypatch):
    """总闸关闭时，即使填了 Key 也不许调用."""
    _configure(monkeypatch, enabled=False, api_key="sk-test")
    assert LLMClient().enabled() is False


def test_disabled_without_key(monkeypatch):
    _configure(monkeypatch, enabled=True, api_key="")
    assert LLMClient().enabled() is False


def test_enabled_requires_both(monkeypatch):
    _configure(monkeypatch, enabled=True, api_key="sk-test")
    assert LLMClient().enabled() is True


def test_complete_returns_none_when_disabled(monkeypatch):
    _configure(monkeypatch, enabled=False)
    assert LLMClient().complete("hello") is None


def test_complete_with_images_falls_back_to_text_without_images(monkeypatch):
    """没有可用图片时退回纯文本调用."""
    _configure(monkeypatch, enabled=True, api_key="sk-test")
    client = LLMClient()
    called = {}

    def fake_complete(prompt: str):
        called["prompt"] = prompt
        return "text-result"

    monkeypatch.setattr(client, "complete", fake_complete)
    assert client.complete_with_images("p", []) == "text-result"
    assert called["prompt"] == "p"


def test_encode_images_skips_missing_and_oversized(tmp_path, monkeypatch):
    small = tmp_path / "ui.png"
    small.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
    huge = tmp_path / "huge.png"
    huge.write_bytes(b"0" * (9 * 1024 * 1024))

    encoded = LLMClient._encode_images(
        [small, huge, tmp_path / "missing.png"]
    )
    assert len(encoded) == 1
    item = encoded[0]
    assert item["type"] == "image_url"
    url = item["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    # 能解回原始字节，说明编码正确
    payload = base64.b64decode(url.split(",", 1)[1])
    assert payload.startswith(b"\x89PNG")


def test_encode_images_caps_count(tmp_path):
    paths = []
    for index in range(10):
        path = tmp_path / f"p{index}.png"
        path.write_bytes(b"\x89PNG" + bytes([index]))
        paths.append(path)
    assert len(LLMClient._encode_images(paths)) == llm_module._MAX_IMAGES


def test_image_mime_type():
    assert image_mime_type("a.png") == "image/png"
    assert image_mime_type("a.JPEG") == "image/jpeg"
    assert image_mime_type("a.webp") == "image/webp"
    # 未知后缀按 png 处理，避免 data URL 前缀非法
    assert image_mime_type("a.unknown") == "image/png"
