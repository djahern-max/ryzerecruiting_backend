# app/api/demo_request.py
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.demo_request import DemoRequest
from app.schemas.demo_request import DemoRequestCreate, DemoRequestResponse
from app.services.email import send_demo_request_notification
from app.services.rate_limit import check_rate_limit, get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/demo-request", tags=["demo-request"])


@router.post("", response_model=DemoRequestResponse, status_code=status.HTTP_201_CREATED)
def create_demo_request(payload: DemoRequestCreate, request: Request, db: Session = Depends(get_db)):
    """
    Public: store a demo request lead and notify Dane. The DB row is the
    lead record — stored before the notification email, so an email
    failure never loses the lead.
    """
    ip = get_client_ip(request)
    if not check_rate_limit(f"ratelimit:demo_request:{ip}", limit=10, window_seconds=3600):
        logger.warning(
            f"[demo-request] Rate limit hit from IP {ip} for email {payload.email}"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )

    if payload.website:
        logger.warning(f"[demo-request] Honeypot tripped from IP {ip} for email {payload.email}")
        return DemoRequestResponse(
            id=0,
            name=payload.name,
            company=payload.company,
            email=payload.email,
            phone=payload.phone,
            message=payload.message,
            created_at=datetime.now(timezone.utc),
        )

    entry = DemoRequest(
        name=payload.name,
        company=payload.company,
        email=payload.email,
        phone=payload.phone,
        message=payload.message,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    logger.info(f"[demo-request] New demo request — {entry.email} ({entry.company})")

    try:
        send_demo_request_notification(
            name=entry.name,
            company=entry.company,
            email=entry.email,
            phone=entry.phone or "",
            message=entry.message or "",
        )
    except Exception as e:
        logger.error(f"[demo-request] Notification email failed for {entry.email}: {e}")

    return entry
