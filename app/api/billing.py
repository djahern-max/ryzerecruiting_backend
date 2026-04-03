# app/api/billing.py
# EP17: Stripe billing endpoints.
# Handles checkout session creation, webhook events, and billing status.

import logging
import stripe

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, RYZE_TENANT
from app.models.tenant import Tenant
from app.models.user import User

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(prefix="/api/billing", tags=["billing"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BillingStatusResponse(BaseModel):
    status: str  # trial | active | expired | cancelled
    trial_ends_at: str | None  # ISO string, None if not on trial
    days_remaining: int | None  # None if not on trial
    stripe_subscription_id: str | None


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_tenant(user: User, db: Session) -> Tenant | None:
    slug = user.tenant_id or RYZE_TENANT
    return db.query(Tenant).filter(Tenant.slug == slug).first()


# ---------------------------------------------------------------------------
# GET /api/billing/status
# Returns current tenant's billing state for the frontend to display.
# ---------------------------------------------------------------------------


@router.get("/status", response_model=BillingStatusResponse)
def get_billing_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant(current_user, db)

    if tenant is None:
        # No tenant row — legacy account or RYZE itself
        return BillingStatusResponse(
            status="active",
            trial_ends_at=None,
            days_remaining=None,
            stripe_subscription_id=None,
        )

    days_remaining = None
    trial_ends_str = None

    if tenant.trial_ends_at:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        delta = tenant.trial_ends_at - now
        days_remaining = max(0, delta.days)
        trial_ends_str = tenant.trial_ends_at.isoformat()

    return BillingStatusResponse(
        status=tenant.status,
        trial_ends_at=trial_ends_str,
        days_remaining=days_remaining,
        stripe_subscription_id=tenant.stripe_subscription_id,
    )


# ---------------------------------------------------------------------------
# POST /api/billing/create-checkout-session
# Creates a Stripe Checkout session and returns the redirect URL.
# ---------------------------------------------------------------------------


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
def create_checkout_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant(current_user, db)

    if tenant and tenant.status == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account already has an active subscription.",
        )

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[
                {
                    "price": settings.STRIPE_PRICE_ID,
                    "quantity": 1,
                }
            ],
            customer_email=current_user.email,
            metadata={
                "tenant_slug": current_user.tenant_id or RYZE_TENANT,
                "user_id": str(current_user.id),
            },
            success_url=f"{settings.FRONTEND_URL}/billing/success",
            cancel_url=f"{settings.FRONTEND_URL}/upgrade",
        )
    except stripe.StripeError as e:
        logger.error(f"[billing] Stripe checkout session error: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create checkout session. Please try again.",
        )

    logger.info(
        f"[billing] Checkout session created for tenant={current_user.tenant_id} "
        f"user={current_user.email}"
    )

    return CheckoutSessionResponse(checkout_url=session.url)


# ---------------------------------------------------------------------------
# POST /api/billing/webhook
# Receives and verifies Stripe webhook events.
# Handles: checkout.session.completed, customer.subscription.deleted
# ---------------------------------------------------------------------------


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.SignatureVerificationError:
        logger.warning("[billing] Webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"[billing] Webhook parse error: {e}")
        raise HTTPException(status_code=400, detail="Webhook error")

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info(f"[billing] Webhook received: {event_type}")

    # ── checkout.session.completed ───────────────────────────────────────
    if event_type == "checkout.session.completed":
        tenant_slug = data.metadata["tenant_slug"] if data.metadata else None
        stripe_customer_id = data.customer
        stripe_subscription_id = data.subscription

        if not tenant_slug:
            logger.warning(
                "[billing] checkout.session.completed missing tenant_slug in metadata"
            )
            return {"status": "ok"}

        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        if not tenant:
            logger.warning(f"[billing] No tenant found for slug={tenant_slug}")
            return {"status": "ok"}

        tenant.status = "active"
        tenant.stripe_customer_id = stripe_customer_id
        tenant.stripe_subscription_id = stripe_subscription_id
        db.commit()

        logger.info(
            f"[billing] Tenant activated — slug={tenant_slug} "
            f"customer={stripe_customer_id} sub={stripe_subscription_id}"
        )

    # ── customer.subscription.deleted ───────────────────────────────────
    elif event_type == "customer.subscription.deleted":
        stripe_subscription_id = data.id

        tenant = (
            db.query(Tenant)
            .filter(Tenant.stripe_subscription_id == stripe_subscription_id)
            .first()
        )

        if not tenant:
            logger.warning(
                f"[billing] No tenant found for sub={stripe_subscription_id}"
            )
            return {"status": "ok"}

        tenant.status = "cancelled"
        db.commit()

        logger.info(f"[billing] Subscription cancelled — slug={tenant.slug}")

    # ── invoice.payment_failed ───────────────────────────────────────────
    elif event_type == "invoice.payment_failed":
        stripe_subscription_id = data.subscription
        logger.warning(
            f"[billing] Payment failed for sub={stripe_subscription_id} — "
            "Stripe will retry. No status change yet."
        )

    else:
        logger.info(f"[billing] Unhandled event type: {event_type}")

    return {"status": "ok"}
