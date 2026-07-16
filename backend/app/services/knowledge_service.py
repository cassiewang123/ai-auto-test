"""知识工程服务：RAG 检索与 Prompt 注入."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.business_rule import BusinessRule
from app.models.defect_pattern import DefectPattern
from app.models.interface_knowledge import InterfaceKnowledge


class KnowledgeService:
    """知识检索与注入服务."""

    # ------------------------------------------------------------------
    # RAG 检索
    # ------------------------------------------------------------------
    def search_knowledge(
        self, query: str, project_id: str | None, db: Session
    ) -> dict:
        """检索相关知识，用于注入 AI 用例生成 Prompt.

        - 关键词匹配缺陷模式（按 occurrence_count 降序，limit 5）
        - 关键词匹配业务规则（limit 5）
        - 关键词匹配接口知识（limit 3）
        - 返回 {"defect_patterns": [...], "business_rules": [...], "interface_knowledge": [...]}
        """
        keywords = [kw for kw in (query or "").split() if kw]

        defects = self._search_defects(keywords, project_id, db)
        rules = self._search_rules(keywords, project_id, db)
        interfaces = self._search_interfaces(keywords, project_id, db)

        return {
            "defect_patterns": [self._defect_to_dict(d) for d in defects],
            "business_rules": [self._rule_to_dict(r) for r in rules],
            "interface_knowledge": [self._iface_to_dict(i) for i in interfaces],
        }

    def _build_keyword_filter(self, column, keywords):
        """构建关键词 OR 条件列表."""
        conditions = []
        for kw in keywords:
            conditions.append(column.like(f"%{kw}%"))
        return conditions

    def _search_defects(
        self, keywords: list[str], project_id: str | None, db: Session
    ) -> list[DefectPattern]:
        """关键词匹配缺陷模式，按出现次数降序."""
        stmt = select(DefectPattern).where(DefectPattern.is_active.is_(True))
        if project_id:
            stmt = stmt.where(DefectPattern.project_id == project_id)
        if keywords:
            conditions = self._build_keyword_filter(DefectPattern.title, keywords) + \
                self._build_keyword_filter(DefectPattern.description, keywords)
            stmt = stmt.where(or_(*conditions))
        return (
            db.execute(
                stmt.order_by(DefectPattern.occurrence_count.desc()).limit(5)
            )
            .scalars()
            .all()
        )

    def _search_rules(
        self, keywords: list[str], project_id: str | None, db: Session
    ) -> list[BusinessRule]:
        """关键词匹配业务规则."""
        stmt = select(BusinessRule).where(BusinessRule.is_active.is_(True))
        if project_id:
            stmt = stmt.where(BusinessRule.project_id == project_id)
        if keywords:
            conditions = self._build_keyword_filter(BusinessRule.title, keywords) + \
                self._build_keyword_filter(BusinessRule.rule_text, keywords)
            stmt = stmt.where(or_(*conditions))
        return db.execute(stmt.limit(5)).scalars().all()

    def _search_interfaces(
        self, keywords: list[str], project_id: str | None, db: Session
    ) -> list[InterfaceKnowledge]:
        """关键词匹配接口知识."""
        stmt = select(InterfaceKnowledge)
        if project_id:
            stmt = stmt.where(InterfaceKnowledge.project_id == project_id)
        if keywords:
            conditions = self._build_keyword_filter(InterfaceKnowledge.interface_path, keywords) + \
                self._build_keyword_filter(InterfaceKnowledge.notes, keywords)
            stmt = stmt.where(or_(*conditions))
        return db.execute(stmt.limit(3)).scalars().all()

    # ------------------------------------------------------------------
    # 序列化辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _defect_to_dict(d: DefectPattern) -> dict:
        return {
            "id": d.id,
            "title": d.title,
            "description": d.description,
            "pattern_type": d.pattern_type,
            "severity": d.severity,
            "occurrence_count": d.occurrence_count,
            "source": d.source,
            "related_interface": d.related_interface,
            "related_case_id": d.related_case_id,
            "project_id": d.project_id,
        }

    @staticmethod
    def _rule_to_dict(r: BusinessRule) -> dict:
        return {
            "id": r.id,
            "title": r.title,
            "rule_text": r.rule_text,
            "rule_type": r.rule_type,
            "module": r.module,
            "source": r.source,
            "priority": r.priority,
            "project_id": r.project_id,
        }

    @staticmethod
    def _iface_to_dict(i: InterfaceKnowledge) -> dict:
        return {
            "id": i.id,
            "interface_path": i.interface_path,
            "method": i.method,
            "field_meanings": i.field_meanings,
            "dependencies": i.dependencies,
            "common_headers": i.common_headers,
            "notes": i.notes,
            "project_id": i.project_id,
        }

    # ------------------------------------------------------------------
    # Prompt 注入
    # ------------------------------------------------------------------
    def inject_knowledge_to_prompt(self, base_prompt: str, knowledge: dict) -> str:
        """将检索到的知识注入 AI 生成 Prompt.

        如果知识为空，返回原 prompt；否则拼接 ## 参考知识 章节.
        """
        if not knowledge:
            return base_prompt

        defects = knowledge.get("defect_patterns", [])
        rules = knowledge.get("business_rules", [])
        interfaces = knowledge.get("interface_knowledge", [])

        if not defects and not rules and not interfaces:
            return base_prompt

        sections: list[str] = ["\n\n## 参考知识\n"]

        if defects:
            sections.append("### 已知缺陷模式:")
            for d in defects:
                sections.append(
                    f"- {d.get('title', '')} "
                    f"(类型: {d.get('pattern_type', 'unknown')}, "
                    f"出现次数: {d.get('occurrence_count', 1)})"
                )

        if rules:
            sections.append("### 业务规则:")
            for r in rules:
                sections.append(f"- {r.get('title', '')}: {r.get('rule_text', '')}")

        if interfaces:
            sections.append("### 接口知识:")
            for i in interfaces:
                sections.append(
                    f"- {i.get('method', '')} {i.get('interface_path', '')}"
                    f"{': ' + i.get('notes') if i.get('notes') else ''}"
                )

        return base_prompt + "\n".join(sections)

    # ------------------------------------------------------------------
    # 缺陷模式提取
    # ------------------------------------------------------------------
    def extract_defect_from_analysis(
        self, case, analysis: dict, db: Session
    ) -> DefectPattern:
        """从 AI 归因结果中提取缺陷模式，自动入库.

        - 检查是否已存在相同模式（title 模糊匹配）
        - 已存在则累加 occurrence_count
        - 不存在则新建
        - 返回 DefectPattern 对象
        """
        root_cause = (analysis.get("root_cause") or "").strip()
        title = root_cause[:256] if root_cause else "未知缺陷"
        category = analysis.get("category", "unknown") or "unknown"
        evidence = analysis.get("evidence", "") or ""
        suggestion = analysis.get("suggestion", "") or ""

        related_case_id = getattr(case, "id", None) if case else None
        project_id = getattr(case, "project_id", None) if case else None

        # 模糊匹配已有模式
        existing = (
            db.execute(
                select(DefectPattern).where(
                    DefectPattern.title.like(f"%{title[:128]}%")
                )
            )
            .scalars()
            .first()
        )

        if existing:
            existing.occurrence_count += 1
            existing.ai_analysis_snapshot = analysis
            db.commit()
            db.refresh(existing)
            return existing

        description = evidence or suggestion or root_cause
        defect = DefectPattern(
            title=title,
            description=description,
            pattern_type=category,
            related_case_id=related_case_id,
            severity="medium",
            source="ai_analysis",
            ai_analysis_snapshot=analysis,
            project_id=project_id,
        )
        db.add(defect)
        db.commit()
        db.refresh(defect)
        return defect

    # ------------------------------------------------------------------
    # 高频缺陷升级为业务规则
    # ------------------------------------------------------------------
    def promote_to_business_rule(
        self, defect: DefectPattern, db: Session
    ) -> BusinessRule:
        """将高频缺陷模式升级为业务规则.

        若已存在同源升级规则则直接返回，避免重复升级.
        """
        existing = (
            db.execute(
                select(BusinessRule).where(
                    BusinessRule.related_defect_id == defect.id,
                    BusinessRule.source == "defect_promoted",
                )
            )
            .scalars()
            .first()
        )
        if existing:
            return existing

        rule = BusinessRule(
            title=f"[自动升级] {defect.title}",
            rule_text=defect.description or defect.title,
            rule_type="exception",
            related_defect_id=defect.id,
            source="defect_promoted",
            project_id=defect.project_id,
            priority="P1",
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule
