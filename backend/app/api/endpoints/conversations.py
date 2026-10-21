"""
Conversation reads and creates for the signed-in user.

Scoped by the backend JWT `sub`, which is users.id.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.database import get_db
from app.db.models import Conversation, Message, User

router = APIRouter()


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    message_count: int
    last_message_at: datetime | None
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    index: int
    role: str
    content: dict | list | None
    status: str


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationList(BaseModel):
    conversations: list[ConversationOut]


def _require_user(db: Session, user: CurrentUser) -> User:
    row = db.get(User, user.sub)
    if row is None:
        raise HTTPException(
            status_code=403,
            detail="Sign out and sign in again to register your account.",
        )
    return row


def _owned_conversation(db: Session, user: CurrentUser, conversation_id: uuid.UUID) -> Conversation:
    _require_user(db, user)
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.sub)
        .one_or_none()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/conversations", response_model=ConversationList)
def list_conversations(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationList:
    _require_user(db, user)
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.sub)
        .order_by(func.coalesce(Conversation.last_message_at, Conversation.created_at).desc())
        .all()
    )
    return ConversationList(conversations=rows)


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    _require_user(db, user)
    conversation = Conversation(user_id=user.sub)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationDetail:
    conversation = _owned_conversation(db, user, conversation_id)
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.index.asc())
        .all()
    )
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        message_count=conversation.message_count,
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
        messages=messages,
    )
