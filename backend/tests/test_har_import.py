"""HAR 抓包导入功能测试."""
from __future__ import annotations

import app.models  # noqa: F401  注册模型元数据
import app.models.db_assertion  # noqa: F401  TestCase 关联 DbAssertion，需显式注册
from app.api.v1.import_api import _suggest_name

HAR_PREVIEW = "/api/v1/import/har/preview"
HAR_IMPORT = "/api/v1/import/har/import"
CASES = "/api/v1/test-cases"


SAMPLE_HAR = {
    "log": {
        "entries": [
            {
                "request": {
                    "method": "POST",
                    "url": "https://api.example.com/api/v1/users/login",
                    "headers": [
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "Cookie", "value": "session=abc"},  # 应被过滤
                    ],
                    "queryString": [],
                    "postData": {"text": '{"username":"test","password":"123"}'},
                },
                "response": {
                    "status": 200,
                    "content": {"text": '{"code":0,"data":{"token":"xxx"}}'},
                },
            },
            {
                "request": {
                    "method": "GET",
                    "url": "https://api.example.com/api/v1/orders/list",
                    "headers": [],
                    "queryString": [{"name": "page", "value": "1"}],
                },
                "response": {
                    "status": 200,
                    "content": {"text": '{"data":[]}', "mimeType": "application/json"},
                },
            },
        ]
    }
}


def _preview(client, har=SAMPLE_HAR, **filters):
    payload = {"har_content": har, **filters}
    resp = client.post(HAR_PREVIEW, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# preview 基础解析
# ---------------------------------------------------------------------------
class TestPreviewHar:
    def test_preview_har_basic(self, client):
        """基本解析 HAR 文件，返回全部接口."""
        data = _preview(client)
        assert data["total"] == 2
        ifaces = data["interfaces"]
        # 第一个：POST /api/v1/users/login
        login = next(i for i in ifaces if i["method"] == "POST")
        assert login["path"] == "/api/v1/users/login"
        assert login["full_url"] == "https://api.example.com/api/v1/users/login"
        assert login["key"] == "POST /api/v1/users/login"
        assert login["response_status"] == 200
        assert login["response_body"] == {"code": 0, "data": {"token": "xxx"}}
        # 第二个：GET /api/v1/orders/list
        orders = next(i for i in ifaces if i["method"] == "GET")
        assert orders["path"] == "/api/v1/orders/list"
        assert orders["params"] == {"page": "1"}

    def test_preview_har_domain_filter(self, client):
        """域名筛选：匹配返回，不匹配返回空."""
        # 匹配域名
        data = _preview(client, domain_filter="api.example.com")
        assert data["total"] == 2
        # 不匹配域名
        data = _preview(client, domain_filter="other.com")
        assert data["total"] == 0
        assert data["interfaces"] == []

    def test_preview_har_method_filter(self, client):
        """方法筛选：只返回指定方法的接口."""
        data = _preview(client, method_filter="POST")
        assert data["total"] == 1
        assert data["interfaces"][0]["method"] == "POST"
        assert data["interfaces"][0]["path"] == "/api/v1/users/login"

        data = _preview(client, method_filter="GET")
        assert data["total"] == 1
        assert data["interfaces"][0]["method"] == "GET"

    def test_preview_har_dedup(self, client):
        """同 method+path 去重，只保留最后一次出现."""
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "method": "GET",
                            "url": "https://api.example.com/api/v1/users/list",
                            "headers": [],
                            "queryString": [{"name": "page", "value": "1"}],
                        },
                        "response": {"status": 200, "content": {"text": "{}"}},
                    },
                    {
                        "request": {
                            "method": "GET",
                            "url": "https://api.example.com/api/v1/users/list",
                            "headers": [],
                            "queryString": [{"name": "page", "value": "2"}],
                        },
                        "response": {"status": 201, "content": {"text": "{}"}},
                    },
                ]
            }
        }
        data = _preview(client, har=har)
        assert data["total"] == 1
        iface = data["interfaces"][0]
        # 应保留最后一次出现的记录
        assert iface["params"] == {"page": "2"}
        assert iface["response_status"] == 201

    def test_preview_har_parse_body(self, client):
        """解析 POST body 为 dict."""
        data = _preview(client)
        login = next(i for i in data["interfaces"] if i["method"] == "POST")
        assert login["body"] == {"username": "test", "password": "123"}
        # GET 请求无 body
        orders = next(i for i in data["interfaces"] if i["method"] == "GET")
        assert orders["body"] is None

    def test_preview_har_parse_headers(self, client):
        """解析 headers，过滤 cookie 和 content-length."""
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "method": "POST",
                            "url": "https://api.example.com/api/v1/users/login",
                            "headers": [
                                {"name": "Content-Type", "value": "application/json"},
                                {"name": "Cookie", "value": "session=abc"},
                                {"name": "Content-Length", "value": "42"},
                                {"name": "Authorization", "value": "Bearer xyz"},
                            ],
                            "queryString": [],
                            "postData": {"text": "{}"},
                        },
                        "response": {"status": 200, "content": {"text": "{}"}},
                    }
                ]
            }
        }
        data = _preview(client, har=har)
        headers = data["interfaces"][0]["headers"]
        assert headers == {
            "Content-Type": "application/json",
            "Authorization": "Bearer xyz",
        }
        assert "Cookie" not in headers
        assert "Content-Length" not in headers
        assert "content-length" not in headers


# ---------------------------------------------------------------------------
# import 批量创建用例
# ---------------------------------------------------------------------------
class TestImportHar:
    def test_import_har(self, client):
        """批量导入创建 TestCase."""
        ifaces = [
            {
                "method": "POST",
                "path": "/api/v1/users/login",
                "full_url": "https://api.example.com/api/v1/users/login",
                "headers": {"Content-Type": "application/json"},
                "params": {},
                "body": {"username": "test", "password": "123"},
                "suggested_name": "创建登录用户",
                "response_status": 200,
            },
            {
                "method": "GET",
                "path": "/api/v1/orders/list",
                "full_url": "https://api.example.com/api/v1/orders/list",
                "headers": {},
                "params": {"page": "1"},
                "body": None,
                "suggested_name": "查询订单列表",
                "response_status": 200,
            },
        ]
        resp = client.post(HAR_IMPORT, json={"selected_interfaces": ifaces})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["created_count"] == 2
        assert len(data["case_ids"]) == 2

        # 验证用例确实被创建
        for i, case_id in enumerate(data["case_ids"]):
            got = client.get(f"{CASES}/{case_id}")
            assert got.status_code == 200
            case = got.json()["data"]
            assert case["method"] == ifaces[i]["method"]
            assert case["url"] == ifaces[i]["path"]
            assert case["title"] == ifaces[i]["suggested_name"]
            assert case["markers"] == ["api", "har_imported"]

    def test_import_har_with_assertions(self, client):
        """导入时自动创建断言规则."""
        ifaces = [
            {
                "method": "POST",
                "path": "/api/v1/users/login",
                "headers": {},
                "params": {},
                "body": None,
                "suggested_name": "登录",
                "response_status": 200,
            }
        ]
        resp = client.post(HAR_IMPORT, json={"selected_interfaces": ifaces})
        assert resp.status_code == 200, resp.text
        case_id = resp.json()["data"]["case_ids"][0]

        got = client.get(f"{CASES}/{case_id}")
        case = got.json()["data"]
        assert len(case["assertions"]) == 1
        a = case["assertions"][0]
        assert a["assertion_type"] == "status_code"
        assert a["operator"] == "eq"
        assert a["expected"] == "200"
        assert a["priority"] == "P0"
        assert a["order"] == 0

    def test_import_har_uses_path_when_no_name(self, client):
        """无 suggested_name 时用 path 作为标题."""
        ifaces = [
            {
                "method": "GET",
                "path": "/api/v1/ping",
                "headers": {},
                "params": {},
                "body": None,
                "response_status": 200,
            }
        ]
        resp = client.post(HAR_IMPORT, json={"selected_interfaces": ifaces})
        assert resp.status_code == 200
        case_id = resp.json()["data"]["case_ids"][0]
        case = client.get(f"{CASES}/{case_id}").json()["data"]
        assert case["title"] == "/api/v1/ping"


# ---------------------------------------------------------------------------
# 名称推断
# ---------------------------------------------------------------------------
class TestSuggestName:
    def test_suggest_name_login(self):
        """POST /login → 创建登录."""
        assert _suggest_name("POST", "/api/v1/users/login") == "创建登录用户"

    def test_suggest_name_orders_list(self):
        """GET /orders/list → 查询订单列表."""
        assert _suggest_name("GET", "/api/v1/orders/list") == "查询订单列表"

    def test_suggest_name_no_match(self):
        """无匹配关键词时使用方法动作 + 接口."""
        assert _suggest_name("GET", "/api/v1/unknown") == "查询接口"

    def test_suggest_name_delete(self):
        """DELETE /products/123 → 删除商品."""
        assert _suggest_name("DELETE", "/api/v1/products/123") == "删除商品"
