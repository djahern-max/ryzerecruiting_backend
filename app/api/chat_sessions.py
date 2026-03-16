# app/api/chat_sessions.py
"""
Chat session persistence endpoints — RYZE Intelligence history.
Follows the ChatGPT/Claude.ai pattern: sessions in sidebar, messages reloadable.
"""
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.bookings import require_admin
from app.core.config import settings
from app.core.database import get_db
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat/sessions", tags=["chat_sessions"])

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SessionCreate(BaseModel):
    title: Optional[str] = None


class SessionTitleUpdate(BaseModel):
    title: str


class MessageIn(BaseModel):
    role: str
    content: str
    structured_data: Optional[str] = None  # JSON string


class MessageOut(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    structured_data: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SessionOut(BaseModel):
    id: int
    user_id: int
    title: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SessionWithMessages(BaseModel):
    id: int
    user_id: int
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    messages: List[MessageOut]

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=SessionOut, status_code=201)
def create_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    session = ChatSession(
        user_id=current_user.id,
        title=payload.title,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("", response_model=List[SessionOut])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )


@router.get("/{session_id}", response_model=SessionWithMessages)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    return {
        "id": session.id,
        "user_id": session.user_id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "messages": messages,
    }


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    db.delete(session)
    db.commit()


@router.patch("/{session_id}", response_model=SessionOut)
def update_session_title(
    session_id: int,
    payload: SessionTitleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    session.title = payload.title
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/messages", response_model=MessageOut, status_code=201)
def save_message(
    session_id: int,
    payload: MessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    message = ChatMessage(
        session_id=session_id,
        role=payload.role,
        content=payload.content,
        structured_data=payload.structured_data,
    )
    db.add(message)

    # Bump session updated_at so sidebar sorts correctly
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(message)
    return message


@router.post("/{session_id}/generate-title", response_model=SessionOut)
def generate_title(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    After first exchange, call this to generate a 4-6 word title via Claude Haiku.
    """
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(2)
        .all()
    )

    if not messages:
        raise HTTPException(status_code=400, detail="No messages to title.")

    exchange = "\n".join([f"{m.role}: {m.content[:200]}" for m in messages])

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[
                {
                    "role": "user",
                    "content": f"Generate a 4-6 word title for this conversation. Return only the title, no punctuation, no quotes:\n\n{exchange}",
                }
            ],
        )
        title = response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Title generation failed: {e}")
        title = messages[0].content[:50] if messages else "New Chat"

    session.title = title
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return session
