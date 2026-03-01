# app/models/waitlist.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class Waitlist(Base):
    __tablename__ = "waitlist"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    source = Column(String(100), nullable=True)  # e.g. "landing_page"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
