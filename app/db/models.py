
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, Integer, JSON, DateTime, Boolean, Index
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional

class Base(DeclarativeBase):
    pass

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False) # user, assistant, system
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True) # ID of the user interacting
    user_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # admin, user
    content: Mapped[str] = mapped_column(Text, nullable=False)
    trace_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Metadata for filtering
    company_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

class WorkflowState(Base):
    __tablename__ = "workflow_state"

    session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    workflow_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    current_step: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    state_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class SQLCache(Base):
    __tablename__ = "sql_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True) # Hash of the user prompt/intent
    generated_sql: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_accessed: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    hit_count: Mapped[int] = mapped_column(Integer, default=0)

    # For validation/invalidation if schema changes
    schema_version: Mapped[str] = mapped_column(String(50), default="v1")

class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str] = mapped_column(String(255), nullable=True) # Assuming separation might be useful, but maintaining existing schema inference
    email: Mapped[str] = mapped_column("email_id", String(255), unique=True, index=True, nullable=False)
    # hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Context
    company_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column("date_created", DateTime(timezone=True), server_default=func.now())
