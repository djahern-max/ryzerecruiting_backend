# app/models/user.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SQLEnum
from datetime import datetime
from app.core.database import Base
import enum


class UserType(str, enum.Enum):
    EMPLOYER = "EMPLOYER"
    CANDIDATE = "CANDIDATE"
    ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=True)  # Nullable for OAuth users
    user_type = Column(SQLEnum(UserType), nullable=False)

    # OAuth fields
    oauth_provider = Column(String, nullable=True)
    oauth_provider_id = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)

    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)

    # Multi-tenancy — which firm this user belongs to ('ryze' = RYZE Recruiting)
    tenant_id = Column(String(100), nullable=True, default="ryze", index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
