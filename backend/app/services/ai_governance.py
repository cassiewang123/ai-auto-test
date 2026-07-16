"""AI 调用治理服务：记录调用、成本、反馈"""
import hashlib, json, time
from sqlalchemy.orm import Session
from app.models.ai_invocation import AIInvocation, AIFeedback


class AIGovernanceService:
    def __init__(self, db: Session):
        self.db = db

    def record_invocation(self, model: str, provider: str, prompt: str,
                          response: str, token_usage: dict, latency_ms: int,
                          cost: float, invoked_by: str = None) -> AIInvocation:
        input_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        invocation = AIInvocation(
            model=model, provider=provider,
            input_hash=input_hash,
            token_usage_input=token_usage.get("input", 0),
            token_usage_output=token_usage.get("output", 0),
            token_usage_total=token_usage.get("total", 0),
            latency_ms=latency_ms,
            cost=cost,
            invoked_by=invoked_by,
        )
        self.db.add(invocation)
        self.db.commit()
        return invocation

    def record_feedback(self, invocation_id: str, accepted: bool = None,
                       edited: bool = None, rejected: bool = None,
                       comment: str = None, rating: int = None,
                       created_by: str = None) -> AIFeedback:
        inv = self.db.get(AIInvocation, invocation_id)
        if inv:
            if accepted is not None: inv.accepted = accepted
            if edited is not None: inv.edited = edited
            if rejected is not None: inv.rejected = rejected
            if comment: inv.feedback_comment = comment
        feedback = AIFeedback(
            invocation_id=invocation_id,
            rating=rating, comment=comment,
            created_by=created_by,
        )
        self.db.add(feedback)
        self.db.commit()
        return feedback

    def get_stats(self, days: int = 30) -> dict:
        """获取 AI 调用统计"""
        from datetime import datetime, timedelta
        since = datetime.now() - timedelta(days=days)
        invocations = self.db.query(AIInvocation).filter(
            AIInvocation.created_at >= since
        ).all()
        total = len(invocations)
        total_cost = sum(i.cost or 0 for i in invocations)
        total_tokens = sum(i.token_usage_total or 0 for i in invocations)
        accepted = sum(1 for i in invocations if i.accepted)
        rejected = sum(1 for i in invocations if i.rejected)
        return {
            "total_invocations": total,
            "total_cost": round(total_cost, 4),
            "total_tokens": total_tokens,
            "accepted": accepted,
            "rejected": rejected,
            "acceptance_rate": round(accepted / total * 100, 1) if total else 0,
        }
