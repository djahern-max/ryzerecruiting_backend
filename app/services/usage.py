# app/services/usage.py
"""
AI usage metering — the single choke point for recording token usage/cost
and enforcing the internal per-tenant monthly AI budget (separate from the
$20/mo subscription). Call sites never compute cost inline.

record_usage() must NEVER raise — every call site invokes it right after an
AI API call returns, including inside sync generators mid-stream and
background tasks, where an unhandled exception would break the request.

check_ai_budget() DOES raise (HTTPException 429, code "ai_usage_limit") — it
is the deliberate gate, called only at synchronous AI-endpoint entry points
where a raise can actually reach the client. Never call it from a background
task — use is_over_budget() there instead for a soft skip.

Imports nothing from app.core.deps — this module is intentionally independent
of deps.py's 402/tenant-access machinery. Budget exemption is read straight
from tenants.billing_exempt.
"""
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tenant import Tenant
from app.models.usage_event import UsageEvent

logger = logging.getLogger(__name__)

# Verified at platform.claude.com/docs/en/about-claude/pricing and
# developers.openai.com/api/docs/models/text-embedding-3-small on 2026-07-27.
# $ per token (converted from $ per MTok). Re-verify before adding/changing models.
PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "claude-haiku-4-5-20251001": {"input": 1.00 / 1_000_000, "output": 5.00 / 1_000_000},
    "text-embedding-3-small": {"input": 0.02 / 1_000_000, "output": 0.0},
}


def _cost_for(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING.get(model)
    if rates is None:
        logger.warning(f"[usage] Unknown model '{model}' — recording tokens, cost=0")
        return 0.0
    return input_tokens * rates["input"] + output_tokens * rates["output"]


def record_usage(
    db: Session,
    tenant_id: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int = 0,
    source: str = "unknown",
) -> None:
    """Record one usage event. Never raises."""
    try:
        cost = _cost_for(model, input_tokens, output_tokens)
        db.add(
            UsageEvent(
                tenant_id=tenant_id,
                provider=provider,
                model=model,
                source=source,
                input_tokens=input_tokens or 0,
                output_tokens=output_tokens or 0,
                cost_usd=Decimal(str(cost)),
            )
        )
        db.commit()
    except Exception as e:
        logger.error(f"[usage] record_usage failed (tenant={tenant_id}, model={model}): {e}")
        try:
            db.rollback()
        except Exception:
            pass


def get_month_cost(db: Session, tenant_id: str, now: Optional[datetime] = None) -> float:
    """Sum cost_usd for tenant_id in the current calendar month, UTC. Never raises."""
    try:
        now = now or datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        total = (
            db.query(func.coalesce(func.sum(UsageEvent.cost_usd), 0))
            .filter(UsageEvent.tenant_id == tenant_id, UsageEvent.created_at >= month_start)
            .scalar()
        )
        return float(total or 0)
    except Exception as e:
        logger.error(f"[usage] get_month_cost failed (tenant={tenant_id}): {e}")
        return 0.0


def _is_billing_exempt(db: Session, tenant_id: str) -> bool:
    row = db.query(Tenant.billing_exempt).filter(Tenant.slug == tenant_id).first()
    return bool(row and row[0])


def is_over_budget(db: Session, tenant_id: str) -> bool:
    """Tenants with billing_exempt=true are never over budget.
    Never raises — fails open (False) on error."""
    try:
        if _is_billing_exempt(db, tenant_id):
            return False
        return get_month_cost(db, tenant_id) >= settings.AI_MONTHLY_BUDGET_USD
    except Exception as e:
        logger.error(f"[usage] is_over_budget failed open (tenant={tenant_id}): {e}")
        return False


def check_ai_budget(db: Session, tenant_id: str) -> None:
    """Raise 429 ai_usage_limit at synchronous AI-endpoint entry points."""
    try:
        if is_over_budget(db, tenant_id):
            spent = get_month_cost(db, tenant_id)
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "ai_usage_limit",
                    "message": (
                        f"This account has used its AI budget for this month "
                        f"(${spent:.2f} of ${settings.AI_MONTHLY_BUDGET_USD:.2f}). "
                        "It resets on the 1st of next month."
                    ),
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[usage] check_ai_budget failed open (tenant={tenant_id}): {e}")
