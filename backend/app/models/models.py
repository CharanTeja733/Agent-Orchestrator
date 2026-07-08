"""SQLAlchemy ORM models for the HR Q&A Agent.

These models mirror the DDL defined in ``app.database.create_tables()`` and
serve as type-hinted wrappers for queries that prefer the ORM over raw SQL.
"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="employee")
    department = Column(String(100), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    sessions = relationship("Session", back_populates="user")
    messages = relationship("Message", back_populates="user")
    feedback = relationship("Feedback", back_populates="user")


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    device_info = Column(JSONB)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(
        DateTime(timezone=True),
        server_default=func.now() + func.text("INTERVAL '24 hours'"),
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session")


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(JSONB)
    confidence = Column(String(20))
    tokens_used = Column(Integer)
    classification = Column(String(30))
    processing_time_ms = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("Session", back_populates="messages")
    user = relationship("User", back_populates="messages")
    feedback = relationship("Feedback", back_populates="message")


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    rating = Column(String(10), nullable=False)
    reason = Column(String(50))
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    message = relationship("Message", back_populates="feedback")
    user = relationship("User", back_populates="feedback")


# ---------------------------------------------------------------------------
# HRDocument
# ---------------------------------------------------------------------------

class HRDocument(Base):
    __tablename__ = "hr_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=False)
    source = Column(String(500), nullable=False)
    page = Column(Integer)
    section = Column(String(500))
    chunk_index = Column(Integer, nullable=False)
    access_level = Column(String(50), nullable=False, default="all")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# ITDocument (Feature 13)
# ---------------------------------------------------------------------------


class ITDocument(Base):
    __tablename__ = "it_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=False)
    source = Column(String(500), nullable=False)
    page = Column(Integer)
    section = Column(String(500))
    chunk_index = Column(Integer, nullable=False)
    access_level = Column(String(50), nullable=False, default="all")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# SystemLog (Feature 11)
# ---------------------------------------------------------------------------

class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    level = Column(String(20), nullable=False)
    component = Column(String(50), nullable=False)
    event = Column(String(100), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    details = Column(JSONB)
    error_trace = Column(Text)
