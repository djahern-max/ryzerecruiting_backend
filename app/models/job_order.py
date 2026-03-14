# app/models/job_order.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class JobOrder(Base):
    __tablename__ = "job_orders"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, default=1, nullable=False)

    employer_profile_id = Column(
        Integer, ForeignKey("employer_profiles.id"), nullable=True
    )

    # Job details
    title = Column(String, nullable=False)
    location = Column(String, nullable=True)
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    requirements = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # Status
    status = Column(String, default="open")  # open | filled | on_hold

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    filled_at = Column(DateTime, nullable=True)

    # Relationships
    employer_profile = relationship("EmployerProfile", backref="job_orders")
