# app/api/job_orders.py
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.models.job_order import JobOrder
from app.api.bookings import require_admin
from app.models.user import User
from app.schemas.job_order import JobOrderCreate, JobOrderUpdate, JobOrderResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/job-orders", tags=["job-orders"])


@router.get("", response_model=List[JobOrderResponse])
def list_job_orders(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(JobOrder).filter(JobOrder.tenant_id == 1)
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
        .filter(JobOrder.id == job_order_id, JobOrder.tenant_id == 1)
        .first()
    )
    if not job_order:
        raise HTTPException(status_code=404, detail="Job order not found.")
    return job_order


@router.post("", response_model=JobOrderResponse, status_code=status.HTTP_201_CREATED)
def create_job_order(
    payload: JobOrderCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    job_order = JobOrder(
        tenant_id=1,
        **payload.model_dump(),
    )
    db.add(job_order)
    db.commit()
    db.refresh(job_order)
    logger.info(f"Job order created: {job_order.title} (#{job_order.id})")
    return job_order


@router.patch("/{job_order_id}", response_model=JobOrderResponse)
def update_job_order(
    job_order_id: int,
    payload: JobOrderUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    job_order = (
        db.query(JobOrder)
        .filter(JobOrder.id == job_order_id, JobOrder.tenant_id == 1)
        .first()
    )
    if not job_order:
        raise HTTPException(status_code=404, detail="Job order not found.")

    update_data = payload.model_dump(exclude_unset=True)

    # Auto-set filled_at when status changes to filled
    if update_data.get("status") == "filled" and job_order.status != "filled":
        update_data["filled_at"] = datetime.utcnow()

    for field, value in update_data.items():
        setattr(job_order, field, value)

    job_order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(job_order)
    return job_order


@router.delete("/{job_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job_order(
    job_order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    job_order = (
        db.query(JobOrder)
        .filter(JobOrder.id == job_order_id, JobOrder.tenant_id == 1)
        .first()
    )
    if not job_order:
        raise HTTPException(status_code=404, detail="Job order not found.")
    db.delete(job_order)
    db.commit()
