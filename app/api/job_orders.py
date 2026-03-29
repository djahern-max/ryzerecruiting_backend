# app/api/job_orders.py
import logging
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.models.job_order import JobOrder
from app.api.bookings import require_admin
from app.models.user import User
from app.schemas.job_order import (
    JobOrderCreate,
    JobOrderUpdate,
    JobOrderResponse,
    JobOrderParseRequest,
    JobOrderParseResponse,
)
from app.services.ai_parser import parse_job_description
from app.services.embedding_service import embed_job_order_background

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/job-orders", tags=["job-orders"])


@router.get("/open", response_model=List[JobOrderResponse])
def list_open_job_orders(db: Session = Depends(get_db)):
    """
    Public endpoint — returns all open job orders.
    No authentication required. Used by candidate and employer dashboards.
    """
    return (
        db.query(JobOrder)
        .filter(JobOrder.status == "open")
        .order_by(JobOrder.created_at.desc())
        .all()
    )


@router.get("", response_model=List[JobOrderResponse])
def list_job_orders(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(JobOrder)
    if status:
        query = query.filter(JobOrder.status == status)
    return query.order_by(JobOrder.created_at.desc()).all()


@router.get("/{job_order_id}", response_model=JobOrderResponse)
def get_job_order(
    job_order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    job_order = (
        db.query(JobOrder)
        .filter(JobOrder.id == job_order_id)
        .first()
    )
    if not job_order:
        raise HTTPException(status_code=404, detail="Job order not found.")
    return job_order


@router.post("", response_model=JobOrderResponse, status_code=status.HTTP_201_CREATED)
def create_job_order(
    payload: JobOrderCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    job_order = JobOrder(**payload.model_dump())
    db.add(job_order)
    db.commit()
    db.refresh(job_order)
    logger.info(f"Job order created: {job_order.title} (#{job_order.id})")
    background_tasks.add_task(embed_job_order_background, job_order.id)
    return job_order


@router.patch("/{job_order_id}", response_model=JobOrderResponse)
def update_job_order(
    job_order_id: int,
    payload: JobOrderUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    job_order = db.query(JobOrder).filter(JobOrder.id == job_order_id).first()
    if not job_order:
        raise HTTPException(status_code=404, detail="Job order not found.")

    update_data = payload.model_dump(exclude_unset=True)

    if update_data.get("status") == "filled" and job_order.status != "filled":
        update_data["filled_at"] = datetime.utcnow()

    for field, value in update_data.items():
        setattr(job_order, field, value)

    job_order.embedding = None
    job_order.embedded_at = None
    job_order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(job_order)

    background_tasks.add_task(embed_job_order_background, job_order.id)
    return job_order


@router.delete("/{job_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job_order(
    job_order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    job_order = db.query(JobOrder).filter(JobOrder.id == job_order_id).first()
    if not job_order:
        raise HTTPException(status_code=404, detail="Job order not found.")
    db.delete(job_order)
    db.commit()


@router.post("/parse", response_model=JobOrderParseResponse)
def parse_job_order(
    payload: JobOrderParseRequest,
    _: User = Depends(require_admin),
):
    """
    Parse a job description into structured fields. Does NOT save.
    """
    if not payload.text or len(payload.text.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="Text is too short to parse. Please paste the full job description.",
        )

    result = parse_job_description(payload.text)
    if not result:
        raise HTTPException(
            status_code=422,
            detail="Could not parse the provided text. Please try again.",
        )
    return result
