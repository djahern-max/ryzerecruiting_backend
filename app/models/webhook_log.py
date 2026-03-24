# app/models/webhook_log.py
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class WebhookLog(Base):
    """
    Persists every raw Zoom webhook payload for debugging and auditing.

    Every event Zoom fires — meeting.ended, recording.completed,
    meeting.summary_updated, or anything else — is written here before
    any processing begins. This lets you inspect exactly what arrived,
    in what order, and with what payload after a real or mock call.

    Visible in DB Explorer under the 'webhook_logs' table.
    """

    __tablename__ = "webhook_logs"

    id = Column(Integer, primary_key=True, index=True)

    # The Zoom event name, e.g. "recording.completed"
    event = Column(String(100), nullable=False, index=True)

    # Numeric meeting ID extracted from payload (for quick filtering)
    meeting_id = Column(String(50), nullable=True, index=True)

    # Meeting UUID (double-base64 encoded, used for AI Companion API calls)
    meeting_uuid = Column(String(255), nullable=True)

    # Full raw JSON payload — the complete body Zoom sent
    raw_payload = Column(Text, nullable=False)

    # Whether our handler found a matching booking in the DB
    booking_found = Column(String(10), nullable=True)  # "yes" | "no" | "n/a"

    # Result of processing: "ok", "no transcript file", "empty download", etc.
    result = Column(String(100), nullable=True)

    # Exact timestamp Zoom's payload hit our endpoint
    received_at = Column(DateTime(timezone=True), server_default=func.now())
