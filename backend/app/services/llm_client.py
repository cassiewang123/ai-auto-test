"""轻量 LLM 客户端：基于 openai SDK，支持文本与多模态（图片）输入.

为什么不直接用 langchain：
    requirements 里虽然声明了 langchain-openai，但本地环境并未安装；而
    ``openai`` SDK 已安装且被其它模块使用。这里直接用 openai SDK，
    避免为了一个invoke 调用引入整套 langchain 依赖。

职责：
    - 统一读取 LLM 配置（模型/Key/网关/温度）
    - 提供 `complete()`（纯文本）与 `complete_with_images()`（文本+图片）
    - 失败时返回 None，由调用方回落到规则引擎，绝不因 LLM 故障中断流程

外部调用总闸：
    ``LLM_EXTERNAL_ENABLED`` 为 False 或 Key 为空时，``enabled()`` 返回
    False，调用方据此走规则引擎，保证「默认不外发数据」。
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# 单张图片超过该大小就不再内联（base64 后会更大，容易被网关拒绝）
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
# 单次请求最多附带的原型图数量
_MAX_IMAGES = 6

_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


def image_mime_type(path: str | Path) -> str:
    return _MIME_BY_SUFFIX.get(Path(path).suffix.lower(), "image/png")


class LLMClient:
    """封装一次 LLM 调用的最小客户端.

    配置来源：本地 ``.env``（LLM_EXTERNAL_ENABLED / OPENAI_API_KEY /
    LLM_MODEL / LLM_BASE_URL）。Key 只存在本机配置文件中，不进入代码仓库，
    也不通过任何接口回传。
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    # ---------------- 可用性 ----------------
    def enabled(self) -> bool:
        """是否允许调用外部 LLM（总闸 + Key 双条件）."""
        return bool(self.settings.LLM_EXTERNAL_ENABLED and self.settings.OPENAI_API_KEY)

    def _client(self):
        """构造 OpenAI 客户端；不可用时返回 None."""
        if not self.enabled():
            return None
        try:
            from openai import OpenAI
        except ImportError:
            logger.warning("未安装 openai SDK，回落到规则引擎")
            return None

        kwargs: dict[str, Any] = {"api_key": self.settings.OPENAI_API_KEY}
        if self.settings.LLM_BASE_URL:
            kwargs["base_url"] = self.settings.LLM_BASE_URL
        try:
            return OpenAI(**kwargs)
        except Exception as exc:  # noqa: BLE001 - 配置错误不应中断流程
            logger.warning("初始化 LLM 客户端失败：%s", exc)
            return None

    def _request_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.settings.LLM_MODEL,
            "temperature": self.settings.LLM_TEMPERATURE,
        }
        max_tokens = self.settings.LLM_MAX_TOKENS
        if max_tokens > 0:
            kwargs["max_tokens"] = max_tokens
        return kwargs

    # ---------------- 调用 ----------------
    def complete(self, prompt: str) -> str | None:
        """纯文本补全；失败返回 None."""
        client = self._client()
        if client is None:
            return None
        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                **self._request_kwargs(),
            )
            return (response.choices[0].message.content or "").strip() or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM 调用失败：%s", exc)
            return None

    def complete_with_images(
        self,
        prompt: str,
        image_paths: list[str | Path] | None = None,
    ) -> str | None:
        """文本 + 图片（页面原型）多模态补全；失败返回 None.

        图片以 base64 data URL 内联，网关无需能公网访问本机文件。
        超过大小上限或数量上限的图片会被跳过，而不是让整次调用失败。
        """
        images = self._encode_images(image_paths)
        if not images:
            return self.complete(prompt)

        client = self._client()
        if client is None:
            return None

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        content.extend(images)
        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": content}],
                **self._request_kwargs(),
            )
            return (response.choices[0].message.content or "").strip() or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("多模态 LLM 调用失败，尝试退回纯文本：%s", exc)
            # 模型不支持图片时退化为纯文本，至少还能利用需求正文
            return self.complete(prompt)

    @staticmethod
    def _encode_images(
        image_paths: list[str | Path] | None,
    ) -> list[dict[str, Any]]:
        encoded: list[dict[str, Any]] = []
        for raw in (image_paths or [])[:_MAX_IMAGES]:
            path = Path(raw)
            try:
                if not path.is_file():
                    continue
                if path.stat().st_size > _MAX_IMAGE_BYTES:
                    logger.info("原型图 %s 超过大小上限，已跳过", path.name)
                    continue
                data = base64.b64encode(path.read_bytes()).decode("ascii")
            except OSError as exc:
                logger.info("读取原型图 %s 失败：%s", path, exc)
                continue
            encoded.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image_mime_type(path)};base64,{data}",
                    },
                }
            )
        return encoded


def get_llm_client() -> LLMClient:
    return LLMClient()
