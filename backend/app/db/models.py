"""
Database models for documents, chunks, and embeddings, plus Auth.js users/accounts
and chat conversations.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, String, Integer, Float, DateTime, ForeignKey, Text, JSON, Boolean, Index, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class Document(Base):
    """
    Stores document metadata with optional embedding information.
    """
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)  # UUID or custom ID
    title = Column(String(255), nullable=False, index=True)
    source = Column(String(512), nullable=True)  # URL, file path, etc.
    doc_metadata = Column(JSON, nullable=True)  # Flexible metadata storage
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False, index=True)  # Soft delete
    
    # Relationships
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document(id={self.id}, title={self.title})>"


class Chunk(Base):
    """
    Stores text chunks extracted from documents.
    """
    __tablename__ = "chunks"

    id = Column(String, primary_key=True, index=True)  # UUID or chunk_id
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)  # Sequence position within document
    text = Column(Text, nullable=False)
    chunk_metadata = Column(JSON, nullable=True)  # Custom metadata for chunk
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False, index=True)  # Soft delete
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    embeddings = relationship("Embedding", back_populates="chunk", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_document_chunk_index", "document_id", "chunk_index"),
    )

    def __repr__(self):
        return f"<Chunk(id={self.id}, document_id={self.document_id}, index={self.chunk_index})>"


class Embedding(Base):
    """
    Stores embedding vectors and related metadata.
    Links chunks to their vector representations.
    """
    __tablename__ = "embeddings"

    id = Column(String, primary_key=True, index=True)
    chunk_id = Column(String, ForeignKey("chunks.id"), nullable=False, index=True)
    vector = Column(Vector(3072), nullable=True)  # pgvector: text-embedding-3-large dimension
    model = Column(String(100), nullable=True)  # Model used (e.g., "text-embedding-3-large")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    chunk = relationship("Chunk", back_populates="embeddings")

    def __repr__(self):
        return f"<Embedding(id={self.id}, chunk_id={self.chunk_id})>"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """Auth.js user. id is a text UUID generated when the account is first linked."""

    __tablename__ = "users"

    id = Column(String, primary_key=True)
    name = Column(Text, nullable=True)
    email = Column(Text, nullable=False, unique=True)
    email_verified = Column("emailVerified", DateTime(timezone=True), nullable=True)
    image = Column(Text, nullable=True)

    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"


class Account(Base):
    """Auth.js account. Primary key is (provider, providerAccountId), not a surrogate id."""

    __tablename__ = "accounts"

    user_id = Column("userId", String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(Text, nullable=False)
    provider = Column(Text, nullable=False)
    provider_account_id = Column("providerAccountId", Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    access_token = Column(Text, nullable=True)
    expires_at = Column(Integer, nullable=True)
    token_type = Column(Text, nullable=True)
    scope = Column(Text, nullable=True)
    id_token = Column(Text, nullable=True)
    session_state = Column(Text, nullable=True)

    user = relationship("User", back_populates="accounts")

    __table_args__ = (
        PrimaryKeyConstraint("provider", "providerAccountId"),
        Index("idx_accounts_user_id", "userId"),
    )

    def __repr__(self):
        return f"<Account(provider={self.provider}, provider_account_id={self.provider_account_id})>"


class Conversation(Base):
    """One chat thread owned by a user. title stays null until a later turn names it."""

    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=True)
    message_count = Column(Integer, nullable=False, default=0)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.index",
    )

    def __repr__(self):
        return f"<Conversation(id={self.id}, user_id={self.user_id})>"


class Message(Base):
    """One turn in a conversation. content holds the answer text and citations."""

    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    index = Column("index", Integer, nullable=False)
    role = Column(Text, nullable=False)
    content = Column(JSONB, nullable=True)
    status = Column(Text, nullable=False, default="pending")

    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        CheckConstraint(
            "status IN ('pending', 'streaming', 'complete', 'error')",
            name="ck_messages_status",
        ),
        Index("idx_messages_conversation_index", "conversation_id", "index", unique=True),
    )

    def __repr__(self):
        return f"<Message(id={self.id}, conversation_id={self.conversation_id}, index={self.index})>"
