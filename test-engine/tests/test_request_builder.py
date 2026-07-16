"""请求构建器单元测试：用 httpx.MockTransport 验证各 HTTP 方法、body 形态、
GraphQL、模板变量渲染、耗时记录、超时与错误处理。"""
from __future__ import annotations

import json

import httpx
import pytest

from app.core.exceptions import ValidationError
from app.schemas.execution import RequestDefinition, ResponseData
from app.services.security.url_policy import URLPolicy
from test_engine.request_builder import RequestBuilder


def make_builder(handler) -> RequestBuilder:
    """用 MockTransport 构造一个不发起真实网络的 RequestBuilder."""
    return RequestBuilder(transport=httpx.MockTransport(handler))


def header_get(headers: dict, name: str):
    """大小写不敏感地取响应头值（HTTP 头本身大小写不敏感）."""
    lname = name.lower()
    for k, v in (headers or {}).items():
        if k.lower() == lname:
            return v
    return None


# ----------------------------- 基本方法 -----------------------------
class TestHttpMethods:
    def test_get_with_params_and_headers(self):
        captured = {}

        def handler(request):
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["accept"] = request.headers.get("accept")
            return httpx.Response(200, json={"ok": True}, headers={"X-Test": "1"})

        resp = make_builder(handler).send(
            RequestDefinition(
                method="GET",
                url="https://api.test/users",
                params={"page": "1", "size": "10"},
                headers={"Accept": "application/json"},
            )
        )
        assert captured["method"] == "GET"
        assert "page=1" in captured["url"]
        assert "size=10" in captured["url"]
        assert captured["accept"] == "application/json"
        assert resp.status_code == 200
        assert resp.body == {"ok": True}
        assert header_get(resp.headers, "X-Test") == "1"
        assert json.loads(resp.text) == {"ok": True}

    def test_post_json_body(self):
        captured = {}

        def handler(request):
            captured["body"] = json.loads(request.content)
            captured["content_type"] = request.headers.get("content-type")
            return httpx.Response(201, json={"id": 1})

        resp = make_builder(handler).send(
            RequestDefinition(method="POST", url="https://api.test/users", body={"name": "alice"})
        )
        assert captured["body"] == {"name": "alice"}
        assert captured["content_type"] == "application/json"
        assert resp.status_code == 201
        assert resp.body == {"id": 1}

    def test_put_request(self):
        captured = {}

        def handler(request):
            captured["method"] = request.method
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"ok": True})

        make_builder(handler).send(
            RequestDefinition(method="PUT", url="https://api.test/users/1", body={"name": "bob"})
        )
        assert captured["method"] == "PUT"
        assert captured["body"] == {"name": "bob"}

    def test_patch_request(self):
        captured = {}

        def handler(request):
            captured["method"] = request.method
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"ok": True})

        make_builder(handler).send(
            RequestDefinition(method="PATCH", url="https://api.test/users/1", body={"name": "carol"})
        )
        assert captured["method"] == "PATCH"
        assert captured["body"] == {"name": "carol"}

    def test_delete_request(self):
        captured = {}

        def handler(request):
            captured["method"] = request.method
            return httpx.Response(204)

        resp = make_builder(handler).send(
            RequestDefinition(method="DELETE", url="https://api.test/users/1")
        )
        assert captured["method"] == "DELETE"
        assert resp.status_code == 204

    def test_lowercase_method_normalized(self):
        captured = {}

        def handler(request):
            captured["method"] = request.method
            return httpx.Response(200, json={"ok": True})

        make_builder(handler).send(RequestDefinition(method="get", url="https://api.test/"))
        assert captured["method"] == "GET"


# ----------------------------- Body 形态 -----------------------------
class TestBodyForms:
    def test_post_form_urlencoded(self):
        captured = {}

        def handler(request):
            captured["content_type"] = request.headers.get("content-type")
            captured["body"] = request.content.decode()
            return httpx.Response(200, json={"ok": True})

        make_builder(handler).send(
            RequestDefinition(
                method="POST",
                url="https://api.test/login",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                body={"username": "alice", "password": "secret"},
            )
        )
        assert "application/x-www-form-urlencoded" in captured["content_type"]
        assert "username=alice" in captured["body"]
        assert "password=secret" in captured["body"]

    def test_file_upload_multipart(self):
        captured = {}

        def handler(request):
            captured["content_type"] = request.headers.get("content-type")
            captured["raw"] = request.content.decode("utf-8", errors="replace")
            return httpx.Response(200, json={"uploaded": True})

        files = [
            {
                "field": "file",
                "filename": "test.txt",
                "content": "hello world",
                "content_type": "text/plain",
            }
        ]
        resp = make_builder(handler).send(
            RequestDefinition(method="POST", url="https://api.test/upload", files=files)
        )
        assert captured["content_type"].startswith("multipart/form-data")
        assert "test.txt" in captured["raw"]
        assert "hello world" in captured["raw"]
        assert resp.body == {"uploaded": True}

    def test_graphql_request(self):
        captured = {}

        def handler(request):
            captured["method"] = request.method
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"data": {"user": {"id": 1}}})

        resp = make_builder(handler).send(
            RequestDefinition(
                method="POST",
                url="https://api.test/graphql",
                graphql_query="query { user { id } }",
                body={"id": 1},
            )
        )
        assert captured["method"] == "POST"
        assert captured["body"]["query"] == "query { user { id } }"
        assert captured["body"]["variables"] == {"id": 1}
        assert resp.body == {"data": {"user": {"id": 1}}}

    def test_graphql_without_variables(self):
        captured = {}

        def handler(request):
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"data": {}})

        make_builder(handler).send(
            RequestDefinition(
                method="POST",
                url="https://api.test/graphql",
                graphql_query="{ ping }",
            )
        )
        assert captured["body"] == {"query": "{ ping }", "variables": {}}


# ----------------------------- 模板变量渲染 -----------------------------
class TestVariableRendering:
    def test_render_in_url_headers_body(self):
        captured = {}

        def handler(request):
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("authorization")
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"ok": True})

        variables = {"base_url": "api.test", "token": "abc123", "user_id": 42}
        make_builder(handler).send(
            RequestDefinition(
                method="POST",
                url="https://{{base_url}}/users/{{user_id}}",
                headers={"Authorization": "Bearer {{token}}"},
                body={"ref": "{{token}}", "id": "{{user_id}}"},
            ),
            variables=variables,
        )
        assert captured["url"] == "https://api.test/users/42"
        assert captured["auth"] == "Bearer abc123"
        assert captured["body"]["ref"] == "abc123"
        # 模板渲染为字符串
        assert captured["body"]["id"] == "42"

    def test_render_with_spaces_around_variable(self):
        captured = {}

        def handler(request):
            captured["url"] = str(request.url)
            return httpx.Response(200, json={"ok": True})

        make_builder(handler).send(
            RequestDefinition(method="GET", url="https://api.test/{{ path }}"),
            variables={"path": "items"},
        )
        assert captured["url"] == "https://api.test/items"

    def test_unknown_variable_left_as_is(self):
        captured = {}

        def handler(request):
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"ok": True})

        # 未知变量保持原样（在 header 上验证，避免 URL 中的 {{ 被 httpx 百分号编码）
        make_builder(handler).send(
            RequestDefinition(
                method="GET",
                url="https://api.test/",
                headers={"Authorization": "Bearer {{missing}}"},
            )
        )
        assert captured["auth"] == "Bearer {{missing}}"

    def test_no_variables_does_not_change_body(self):
        captured = {}

        def handler(request):
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"ok": True})

        make_builder(handler).send(
            RequestDefinition(method="POST", url="https://api.test/", body={"name": "alice"})
        )
        assert captured["body"] == {"name": "alice"}


# ----------------------------- 响应解析 / 耗时 -----------------------------
class TestResponseAndTiming:
    def test_elapsed_recorded(self):
        def handler(request):
            return httpx.Response(200, json={"ok": True})

        resp = make_builder(handler).send(RequestDefinition(method="GET", url="https://api.test/"))
        assert isinstance(resp, ResponseData)
        assert isinstance(resp.elapsed, float)
        assert resp.elapsed >= 0

    def test_non_json_body_is_text(self):
        def handler(request):
            return httpx.Response(
                200, content=b"<html>hello</html>", headers={"Content-Type": "text/html"}
            )

        resp = make_builder(handler).send(RequestDefinition(method="GET", url="https://api.test/"))
        assert resp.status_code == 200
        assert resp.body == "<html>hello</html>"
        assert resp.text == "<html>hello</html>"

    def test_error_status_does_not_raise(self):
        def handler(request):
            return httpx.Response(500, json={"error": "boom"})

        resp = make_builder(handler).send(RequestDefinition(method="GET", url="https://api.test/"))
        assert resp.status_code == 500
        assert resp.body == {"error": "boom"}


# ----------------------------- 超时 / 错误 -----------------------------
class TestTimeoutAndErrors:
    def test_timeout_exception_propagates(self):
        def handler(request):
            raise httpx.ReadTimeout("simulated timeout", request=request)

        with pytest.raises(httpx.TimeoutException):
            make_builder(handler).send(
                RequestDefinition(method="GET", url="https://api.test/", timeout=0.001)
            )

    def test_connection_error_propagates(self):
        def handler(request):
            raise httpx.ConnectError("no connection", request=request)

        with pytest.raises(httpx.ConnectError):
            make_builder(handler).send(RequestDefinition(method="GET", url="https://api.test/"))


# ----------------------------- URL 策略 / SSRF 防护 -----------------------------
class TestURLPolicyIntegration:
    """SEC-05: URLPolicy 集成测试."""

    def test_rejects_file_protocol(self):
        """file:// 协议被 URLPolicy 拒绝，抛出 ValidationError."""
        policy = URLPolicy(allow_private=True)
        builder = RequestBuilder(
            transport=httpx.MockTransport(lambda req: httpx.Response(200)),
            url_policy=policy,
        )
        with pytest.raises(ValidationError, match="URL 策略拒绝"):
            builder.send(
                RequestDefinition(method="GET", url="file:///etc/passwd")
            )

    def test_rejects_cloud_metadata(self):
        """169.254.169.254 始终被拒绝."""
        policy = URLPolicy(allow_private=True)
        builder = RequestBuilder(
            transport=httpx.MockTransport(lambda req: httpx.Response(200)),
            url_policy=policy,
        )
        with pytest.raises(ValidationError, match="URL 策略拒绝"):
            builder.send(
                RequestDefinition(
                    method="GET", url="http://169.254.169.254/latest/meta-data/"
                )
            )

    def test_allows_loopback_in_dev_mode(self):
        """开发模式 allow_private=True 允许 127.0.0.1."""
        policy = URLPolicy(allow_private=True)

        def handler(request):
            return httpx.Response(200, json={"ok": True})

        builder = RequestBuilder(
            transport=httpx.MockTransport(handler), url_policy=policy
        )
        resp = builder.send(
            RequestDefinition(method="GET", url="http://127.0.0.1:8000/")
        )
        assert resp.status_code == 200
        assert resp.body == {"ok": True}

    def test_no_validation_when_policy_is_none(self):
        """无 url_policy 时不校验，保持向后兼容（测试用 MockTransport 域名）."""

        def handler(request):
            return httpx.Response(200, json={"ok": True})

        builder = RequestBuilder(transport=httpx.MockTransport(handler))
        resp = builder.send(
            RequestDefinition(method="GET", url="https://api.test/")
        )
        assert resp.status_code == 200

    def test_redirect_to_blocked_ip_rejected(self):
        """重定向到 169.254.169.254 被拒绝."""
        policy = URLPolicy(allow_private=True)
        call_count = [0]

        def handler(request):
            call_count[0] += 1
            if call_count[0] == 1:
                return httpx.Response(
                    302, headers={"Location": "http://169.254.169.254/"}
                )
            return httpx.Response(200, json={"ok": True})

        builder = RequestBuilder(
            transport=httpx.MockTransport(handler), url_policy=policy
        )
        with pytest.raises(ValidationError, match="URL 策略拒绝"):
            builder.send(
                RequestDefinition(method="GET", url="http://127.0.0.1:8000/")
            )

    def test_valid_redirect_followed(self):
        """合法重定向被跟随，最终返回 200."""
        policy = URLPolicy(allow_private=True)
        call_count = [0]

        def handler(request):
            call_count[0] += 1
            if call_count[0] == 1:
                return httpx.Response(
                    302, headers={"Location": "http://127.0.0.1:8000/new"}
                )
            return httpx.Response(200, json={"redirected": True})

        builder = RequestBuilder(
            transport=httpx.MockTransport(handler), url_policy=policy
        )
        resp = builder.send(
            RequestDefinition(method="GET", url="http://127.0.0.1:8000/")
        )
        assert resp.status_code == 200
        assert resp.body == {"redirected": True}
        assert call_count[0] == 2


# ----------------------------- 响应大小限制 -----------------------------
class TestMaxResponseSize:
    """FIX-03: 响应体大小限制."""

    def test_oversized_response_rejected(self):
        """响应超过 max_response_size 时抛出 ValidationError."""

        def handler(request):
            return httpx.Response(200, content=b"x" * 200)

        builder = RequestBuilder(
            transport=httpx.MockTransport(handler), max_response_size=100
        )
        with pytest.raises(ValidationError, match="响应体过大"):
            builder.send(
                RequestDefinition(method="GET", url="http://127.0.0.1:8000/")
            )

    def test_small_response_allowed(self):
        """响应在限制内时正常返回."""

        def handler(request):
            return httpx.Response(200, content=b"x" * 50)

        builder = RequestBuilder(
            transport=httpx.MockTransport(handler), max_response_size=100
        )
        resp = builder.send(
            RequestDefinition(method="GET", url="http://127.0.0.1:8000/")
        )
        assert resp.status_code == 200

    def test_default_max_size_allows_normal_response(self):
        """默认 10MB 限制允许正常响应."""

        def handler(request):
            return httpx.Response(200, json={"ok": True})

        builder = RequestBuilder(transport=httpx.MockTransport(handler))
        resp = builder.send(
            RequestDefinition(method="GET", url="https://api.test/")
        )
        assert resp.status_code == 200
