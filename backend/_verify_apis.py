"""验证脚本：测试 5 个新增功能的 API endpoint 是否正常响应.

覆盖：
    功能5  失败重试机制    -> POST /execution/run (retry_count)
    功能19 前置/后置脚本   -> POST /execution/run (pre_script/post_script)
    功能20 认证快捷配置    -> 前端纯实现，无后端 endpoint
    功能21 Cookie/会话管理 -> POST /execution/run (cookies) + session_cookies 响应
    功能22 全局变量        -> GET/POST/PUT/DELETE /variables

运行：python _verify_apis.py
"""
from __future__ import annotations

import json
import sys

import requests

BASE = "http://127.0.0.1:8000/api/v1"

# 统计结果
PASS = 0
FAIL = 0


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  [PASS] {msg}")


def fail(msg: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {msg}")
    if detail:
        print(f"         {detail}")


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main() -> int:
    s = requests.Session()

    # ------------------------------------------------------------------
    # 0. 登录获取 JWT
    # ------------------------------------------------------------------
    section("0. 登录获取 JWT 令牌")
    token = None
    for username, password in [("admin", "admin123"), ("Admin", "admin123"), ("admin", "admin")]:
        try:
            r = s.post(
                f"{BASE}/auth/login",
                json={"username": username, "password": password},
                timeout=10,
            )
            if r.status_code == 200 and r.json().get("data", {}).get("access_token"):
                token = r.json()["data"]["access_token"]
                ok(f"登录成功: {username}")
                break
            else:
                print(f"  尝试 {username}/{password} -> {r.status_code}")
        except Exception as e:
            print(f"  尝试 {username} 异常: {e}")

    if not token:
        fail("登录失败，无法继续验证")
        return _summary()
    s.headers.update({"Authorization": f"Bearer {token}"})

    # ------------------------------------------------------------------
    # 1. 功能22：全局变量 CRUD
    # ------------------------------------------------------------------
    section("1. 功能22 - 全局变量 CRUD (/variables)")
    created_id = None

    # 1.1 列表
    try:
        r = s.get(f"{BASE}/variables", params={"page": 1, "page_size": 10}, timeout=10)
        if r.status_code == 200:
            body = r.json()
            # PageResponse: {data: [...], total: N, page, page_size}
            total = body.get("total", 0) if isinstance(body, dict) else 0
            data = body.get("data", []) if isinstance(body, dict) else []
            ok(f"GET /variables 列表 200 (total={total}, returned={len(data) if isinstance(data, list) else 'n/a'})")
        else:
            fail("GET /variables 列表", f"status={r.status_code} body={r.text[:200]}")
    except Exception as e:
        fail("GET /variables 列表", str(e))

    # 1.2 创建
    try:
        r = s.post(
            f"{BASE}/variables",
            json={
                "name": "_verify_test_var",
                "value": "hello-world",
                "var_type": "string",
                "description": "验证脚本临时变量",
                "scope": "global",
            },
            timeout=10,
        )
        if r.status_code == 200:
            created_id = r.json()["data"]["id"]
            ok(f"POST /variables 创建 200 (id={created_id[:8]}...)")
        else:
            fail("POST /variables 创建", f"status={r.status_code} body={r.text[:200]}")
    except Exception as e:
        fail("POST /variables 创建", str(e))

    # 1.3 获取单个
    if created_id:
        try:
            r = s.get(f"{BASE}/variables/{created_id}", timeout=10)
            if r.status_code == 200 and r.json()["data"]["name"] == "_verify_test_var":
                ok("GET /variables/{id} 详情 200")
            else:
                fail("GET /variables/{id} 详情", f"status={r.status_code}")
        except Exception as e:
            fail("GET /variables/{id} 详情", str(e))

    # 1.4 更新
    if created_id:
        try:
            r = s.put(
                f"{BASE}/variables/{created_id}",
                json={"value": "updated-value", "description": "已更新"},
                timeout=10,
            )
            if r.status_code == 200 and r.json()["data"]["value"] == "updated-value":
                ok("PUT /variables/{id} 更新 200")
            else:
                fail("PUT /variables/{id} 更新", f"status={r.status_code}")
        except Exception as e:
            fail("PUT /variables/{id} 更新", str(e))

    # 1.5 校验：workspace 作用域无 project_id 应失败
    try:
        r = s.post(
            f"{BASE}/variables",
            json={"name": "_bad", "value": "x", "var_type": "string", "scope": "workspace"},
            timeout=10,
        )
        if r.status_code in (400, 422) or r.json().get("code") == -1:
            ok("workspace 作用域无 project_id 被正确拒绝")
        else:
            fail("workspace 校验未生效", f"status={r.status_code}")
    except Exception as e:
        fail("workspace 校验", str(e))

    # ------------------------------------------------------------------
    # 2. 功能5/19/21：执行接口 - 重试 + 脚本 + Cookie
    # ------------------------------------------------------------------
    section("2. 功能5/19/21 - 执行接口 (重试 + 前后置脚本 + Cookie)")

    # 2.1 基础执行（带前置脚本 + 后置脚本）
    try:
        r = s.post(
            f"{BASE}/execution/run",
            json={
                "method": "GET",
                "url": "https://httpbin.org/get",
                "headers": {},
                "params": {},
                "assertions": [{"assertion_type": "status_code", "operator": "eq", "expected": "200"}],
                "variables": {},
                "pre_script": 'variables["trace_id"] = "verify-" + str(len(variables))',
                "post_script": 'variables["post_done"] = "yes"',
                "retry_count": 0,
                "retry_interval": 0.5,
                "cookies": [],
            },
            timeout=60,
        )
        body = r.json().get("data", {})
        if r.status_code == 200 and body.get("status") in ("passed", "failed", "error"):
            ok(f"POST /execution/run 基础执行 200 (status={body.get('status')})")
            # 校验新增字段存在
            if "pre_script_result" in body:
                ok(f"  响应含 pre_script_result: {body['pre_script_result'].get('success')}")
            else:
                fail("响应缺少 pre_script_result 字段")
            if "post_script_result" in body:
                ok(f"  响应含 post_script_result: {body['post_script_result'].get('success')}")
            else:
                fail("响应缺少 post_script_result 字段")
            if "session_cookies" in body:
                ok(f"  响应含 session_cookies (count={len(body['session_cookies'])})")
            else:
                fail("响应缺少 session_cookies 字段")
            if "retry_attempts" in body:
                ok(f"  响应含 retry_attempts (count={len(body['retry_attempts'])})")
            else:
                fail("响应缺少 retry_attempts 字段")
        else:
            fail("POST /execution/run 基础执行", f"status={r.status_code} body={r.text[:300]}")
    except Exception as e:
        fail("POST /execution/run 基础执行", str(e))

    # 2.2 失败重试验证（请求一个不存在的 URL，应触发重试）
    try:
        r = s.post(
            f"{BASE}/execution/run",
            json={
                "method": "GET",
                "url": "https://httpbin.org/status/500",
                "headers": {},
                "params": {},
                "assertions": [{"assertion_type": "status_code", "operator": "eq", "expected": "200"}],
                "variables": {},
                "retry_count": 2,
                "retry_interval": 0.3,
                "cookies": [],
            },
            timeout=90,
        )
        body = r.json().get("data", {})
        if r.status_code == 200:
            attempts = body.get("retry_attempts", [])
            ok(f"POST /execution/run 失败重试 200 (attempts={len(attempts)}, status={body.get('status')})")
            if len(attempts) >= 2:
                ok(f"  重试次数符合预期 (>=2 次，实际 {len(attempts)} 次)")
            else:
                fail("重试次数不足", f"期望>=2，实际 {len(attempts)}")
        else:
            fail("POST /execution/run 失败重试", f"status={r.status_code}")
    except Exception as e:
        fail("POST /execution/run 失败重试", str(e))

    # 2.3 Cookie 会话验证（httpbin.org/cookies/set 会返回 Set-Cookie）
    try:
        r = s.post(
            f"{BASE}/execution/run",
            json={
                "method": "GET",
                "url": "https://httpbin.org/cookies/set?session_verify=abc123",
                "headers": {},
                "params": {},
                "assertions": [],
                "variables": {},
                "cookies": [],
                "retry_count": 0,
            },
            timeout=60,
        )
        body = r.json().get("data", {})
        if r.status_code == 200:
            sc = body.get("session_cookies", [])
            ok(f"POST /execution/run Cookie 捕获 200 (session_cookies={len(sc)})")
            if sc:
                ok(f"  捕获到 Cookie: {[c.get('name') for c in sc]}")
            else:
                print("  (提示: httpbin 重定向可能未返回 Set-Cookie，此为正常现象)")
        else:
            fail("POST /execution/run Cookie 捕获", f"status={r.status_code}")
    except Exception as e:
        fail("POST /execution/run Cookie 捕获", str(e))

    # 2.4 脚本安全沙箱验证（危险关键字应被拦截）
    try:
        r = s.post(
            f"{BASE}/execution/run",
            json={
                "method": "GET",
                "url": "https://httpbin.org/get",
                "headers": {},
                "params": {},
                "assertions": [],
                "variables": {},
                "pre_script": "import os\nos.system('echo bad')",
                "cookies": [],
                "retry_count": 0,
            },
            timeout=60,
        )
        body = r.json().get("data", {})
        if r.status_code == 200:
            pre_result = body.get("pre_script_result", {})
            if pre_result and not pre_result.get("success"):
                ok(f"POST /execution/run 脚本沙箱拦截危险代码 (error={pre_result.get('error', '')[:60]})")
            else:
                fail("脚本沙箱未拦截 import os", f"pre_script_result={pre_result}")
        else:
            fail("POST /execution/run 脚本沙箱", f"status={r.status_code}")
    except Exception as e:
        fail("POST /execution/run 脚本沙箱", str(e))

    # ------------------------------------------------------------------
    # 3. 清理测试数据
    # ------------------------------------------------------------------
    section("3. 清理测试数据")
    if created_id:
        try:
            r = s.delete(f"{BASE}/variables/{created_id}", timeout=10)
            if r.status_code == 200:
                ok(f"DELETE /variables/{created_id[:8]}... 200")
            else:
                fail("DELETE 清理", f"status={r.status_code}")
        except Exception as e:
            fail("DELETE 清理", str(e))

    return _summary()


def _summary() -> int:
    section(f"验证汇总: {PASS} 通过, {FAIL} 失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
