from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="employee")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sessions = relationship("ChatSession", back_populates="user")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    bucket = Column(String, nullable=False)
    file_hash = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="uploaded")
    error_message = Column(Text, nullable=True)
    page_count = Column(Integer, default=0)
    version = Column(Integer, default=1)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chunks = relationship("Chunk", back_populates="document")


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    chunk_hash = Column(String, nullable=False, index=True)
    page = Column(Integer, nullable=False)
    section = Column(String, default="General")
    text = Column(Text, nullable=False)
    token_estimate = Column(Integer, default=0)

    document = relationship("Document", back_populates="chunks")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session")


class PinnedChatSession(Base):
    __tablename__ = "pinned_chat_sessions"
    __table_args__ = (UniqueConstraint("user_id", "session_id"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    citations_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="messages")


class AnswerCache(Base):
    __tablename__ = "answer_cache"

    id = Column(Integer, primary_key=True, index=True)
    question_hash = Column(String, nullable=False, index=True)
    bucket = Column(String, nullable=False)
    answer_json = Column(Text, nullable=False)
    kb_version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
