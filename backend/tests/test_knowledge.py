"""知识工程 API 测试：缺陷模式、业务规则、接口知识的 CRUD + RAG 检索 + 自进化提取."""
from __future__ import annotations

import app.models  # noqa: F401  注册已有模型元数据
from app.models.business_rule import BusinessRule  # noqa: F401
from app.models.defect_pattern import DefectPattern  # noqa: F401
from app.models.interface_knowledge import InterfaceKnowledge  # noqa: F401
from app.models.test_result import TestResult  # noqa: F401

BASE = "/api/v1/knowledge"


# ---------------------------------------------------------------------------
# 缺陷模式 CRUD
# ---------------------------------------------------------------------------
def _create_defect(client, **overrides):
    payload = {
        "title": "Token 过期导致认证失败",
        "description": "401 Unauthorized，token 过期未刷新",
        "pattern_type": "auth",
        "severity": "high",
    }
    payload.update(overrides)
    resp = client.post(f"{BASE}/defects", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestDefectCRUD:
    def test_create_defect(self, client):
        data = _create_defect(client)
        assert data["id"]
        assert data["title"] == "Token 过期导致认证失败"
        assert data["pattern_type"] == "auth"
        assert data["severity"] == "high"
        assert data["occurrence_count"] == 1
        assert data["source"] == "ai_analysis"
        assert data["is_active"] is True

    def test_list_defects(self, client):
        _create_defect(client, title="缺陷A")
        _create_defect(client, title="缺陷B")
        resp = client.get(f"{BASE}/defects")
        body = resp.json()
        assert body["total"] == 2
        assert len(body["data"]) == 2

    def test_list_defects_filter_by_type(self, client):
        _create_defect(client, pattern_type="auth")
        _create_defect(client, pattern_type="boundary", title="边界错误")
        resp = client.get(f"{BASE}/defects", params={"pattern_type": "auth"})
        body = resp.json()
        assert body["total"] == 1
        assert body["data"][0]["pattern_type"] == "auth"

    def test_update_defect(self, client):
        defect = _create_defect(client)
        resp = client.put(
            f"{BASE}/defects/{defect['id']}",
            json={"severity": "critical", "occurrence_count": 5},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["severity"] == "critical"
        assert data["occurrence_count"] == 5
        # 未更新字段保留
        assert data["title"] == defect["title"]

    def test_update_defect_not_found(self, client):
        resp = client.put(f"{BASE}/defects/nope", json={"severity": "low"})
        assert resp.status_code == 404

    def test_delete_defect(self, client):
        defect = _create_defect(client)
        resp = client.delete(f"{BASE}/defects/{defect['id']}")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        # 确认已删除
        resp = client.get(f"{BASE}/defects")
        assert resp.json()["total"] == 0

    def test_delete_defect_not_found(self, client):
        assert client.delete(f"{BASE}/defects/nope").status_code == 404


# ---------------------------------------------------------------------------
# 业务规则 CRUD
# ---------------------------------------------------------------------------
def _create_rule(client, **overrides):
    payload = {
        "title": "登录接口必须校验token",
        "rule_text": "所有需要登录的接口必须校验token有效性",
        "rule_type": "security",
        "priority": "P0",
    }
    payload.update(overrides)
    resp = client.post(f"{BASE}/rules", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestRuleCRUD:
    def test_create_rule(self, client):
        data = _create_rule(client)
        assert data["id"]
        assert data["title"] == "登录接口必须校验token"
        assert data["rule_type"] == "security"
        assert data["priority"] == "P0"
        assert data["source"] == "manual"
        assert data["is_active"] is True

    def test_list_rules(self, client):
        _create_rule(client, title="规则A")
        _create_rule(client, title="规则B")
        resp = client.get(f"{BASE}/rules")
        body = resp.json()
        assert body["total"] == 2

    def test_list_rules_filter_by_type(self, client):
        _create_rule(client, rule_type="boundary")
        _create_rule(client, rule_type="security", title="安全规则")
        resp = client.get(f"{BASE}/rules", params={"rule_type": "security"})
        body = resp.json()
        assert body["total"] == 1

    def test_delete_rule(self, client):
        rule = _create_rule(client)
        resp = client.delete(f"{BASE}/rules/{rule['id']}")
        assert resp.status_code == 200
        assert client.get(f"{BASE}/rules").json()["total"] == 0

    def test_delete_rule_not_found(self, client):
        assert client.delete(f"{BASE}/rules/nope").status_code == 404


# ---------------------------------------------------------------------------
# 接口知识 CRUD
# ---------------------------------------------------------------------------
def _create_interface(client, **overrides):
    payload = {
        "interface_path": "/api/v1/users/login",
        "method": "POST",
        "notes": "用户登录接口，返回 JWT token",
        "field_meanings": {"token": "访问令牌", "expires_in": "过期秒数"},
    }
    payload.update(overrides)
    resp = client.post(f"{BASE}/interfaces", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestInterfaceCRUD:
    def test_create_interface(self, client):
        data = _create_interface(client)
        assert data["id"]
        assert data["interface_path"] == "/api/v1/users/login"
        assert data["method"] == "POST"
        assert data["field_meanings"]["token"] == "访问令牌"
        assert data["source"] == "manual"

    def test_list_interfaces(self, client):
        _create_interface(client, interface_path="/api/login")
        _create_interface(client, interface_path="/api/logout")
        resp = client.get(f"{BASE}/interfaces")
        body = resp.json()
        assert body["total"] == 2

    def test_delete_interface(self, client):
        item = _create_interface(client)
        resp = client.delete(f"{BASE}/interfaces/{item['id']}")
        assert resp.status_code == 200
        assert client.get(f"{BASE}/interfaces").json()["total"] == 0

    def test_delete_interface_not_found(self, client):
        assert client.delete(f"{BASE}/interfaces/nope").status_code == 404


# ---------------------------------------------------------------------------
# RAG 检索
# ---------------------------------------------------------------------------
class TestSearchKnowledge:
    def test_search_knowledge(self, client):
        """RAG 检索应返回匹配的关键词相关知识."""
        _create_defect(client, title="token过期", description="认证失败")
        _create_rule(client, title="token校验", rule_text="必须校验token")
        _create_interface(client, interface_path="/api/login", notes="token登录")

        resp = client.post(f"{BASE}/search", params={"query": "token"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "defect_patterns" in data
        assert "business_rules" in data
        assert "interface_knowledge" in data
        # 至少匹配到缺陷模式
        assert len(data["defect_patterns"]) >= 1
        assert len(data["business_rules"]) >= 1
        assert len(data["interface_knowledge"]) >= 1

    def test_search_no_match(self, client):
        """无匹配关键词时返回空列表."""
        _create_defect(client, title="token过期")
        resp = client.post(f"{BASE}/search", params={"query": "完全不存在的关键词"})
        data = resp.json()["data"]
        assert data["defect_patterns"] == []
        assert data["business_rules"] == []
        assert data["interface_knowledge"] == []


# ---------------------------------------------------------------------------
# 从分析结果提取缺陷模式
# ---------------------------------------------------------------------------
class TestExtractDefect:
    def test_extract_defect(self, client, db_session):
        """从 TestResult 的 AI 归因结果中提取缺陷模式."""
        from app.models.test_case import TestCase

        # 创建用例
        case = TestCase(
            title="登录测试",
            method="POST",
            url="/api/login",
        )
        db_session.add(case)
        db_session.flush()

        # 创建带 AI 归因的 TestResult
        analysis = {
            "root_cause": "token 过期",
            "evidence": "401 Unauthorized",
            "category": "auth",
            "suggestion": "刷新 token",
            "confidence": 0.9,
        }
        result = TestResult(
            run_id="run-1",
            test_case_id=case.id,
            status="failed",
            ai_analysis=analysis,
        )
        db_session.add(result)
        db_session.commit()

        resp = client.post(
            f"{BASE}/defects/extract", params={"test_result_id": result.id}
        )
        assert resp.status_code == 200, resp.text
        defect = resp.json()["data"]
        assert defect["title"] == "token 过期"
        assert defect["pattern_type"] == "auth"
        assert defect["source"] == "ai_analysis"

    def test_extract_defect_no_analysis(self, client, db_session):
        """TestResult 无 AI 归因时返回 404."""
        from app.models.test_case import TestCase

        case = TestCase(title="测试", method="GET", url="/api/x")
        db_session.add(case)
        db_session.flush()
        result = TestResult(
            run_id="run-2",
            test_case_id=case.id,
            status="failed",
        )
        db_session.add(result)
        db_session.commit()

        resp = client.post(
            f"{BASE}/defects/extract", params={"test_result_id": result.id}
        )
        assert resp.status_code == 404

    def test_extract_defect_not_found(self, client):
        """TestResult 不存在时返回 404."""
        resp = client.post(
            f"{BASE}/defects/extract", params={"test_result_id": "nope"}
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 高频缺陷自动升级为业务规则
# ---------------------------------------------------------------------------
class TestPromoteRules:
    def test_promote_rules(self, client, db_session):
        """高频缺陷模式自动升级为业务规则."""
        # 创建出现次数为 5 的缺陷模式（> 默认阈值 3）
        defect = DefectPattern(
            title="高频认证失败",
            description="反复出现 401 错误",
            pattern_type="auth",
            occurrence_count=5,
            source="ai_analysis",
        )
        db_session.add(defect)
        db_session.commit()

        resp = client.post(f"{BASE}/rules/promote")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["promoted_count"] == 1
        assert len(data["rule_ids"]) == 1

        # 验证业务规则已创建
        rules = db_session.query(BusinessRule).all()
        assert len(rules) == 1
        assert rules[0].source == "defect_promoted"
        assert rules[0].related_defect_id == defect.id

    def test_promote_rules_below_threshold(self, client, db_session):
        """出现次数低于阈值的不升级."""
        defect = DefectPattern(
            title="低频问题",
            description="仅出现一次",
            pattern_type="boundary",
            occurrence_count=2,
        )
        db_session.add(defect)
        db_session.commit()

        resp = client.post(f"{BASE}/rules/promote")
        assert resp.status_code == 200
        assert resp.json()["data"]["promoted_count"] == 0

    def test_promote_rules_custom_threshold(self, client, db_session):
        """自定义阈值."""
        defect = DefectPattern(
            title="中频问题",
            description="出现两次",
            pattern_type="auth",
            occurrence_count=2,
        )
        db_session.add(defect)
        db_session.commit()

        # threshold=1，出现次数 2 > 1，应升级
        resp = client.post(f"{BASE}/rules/promote", params={"threshold": 1})
        assert resp.json()["data"]["promoted_count"] == 1
