from __future__ import annotations

from datetime import datetime  # noqa: TC003 — used in mapped_column DateTime at runtime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PatternRow(Base):
    __tablename__ = "patterns"
    id: Mapped[int] = mapped_column(primary_key=True)
    variable_type: Mapped[str] = mapped_column(String(100), index=True)
    spec_logic: Mapped[str] = mapped_column(Text)
    approved_code: Mapped[str] = mapped_column(Text)
    study: Mapped[str] = mapped_column(String(100))
    approach: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeedbackRow(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    variable: Mapped[str] = mapped_column(String(100), index=True)
    feedback: Mapped[str] = mapped_column(Text)
    action_taken: Mapped[str] = mapped_column(String(200))
    study: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QCHistoryRow(Base):
    __tablename__ = "qc_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    variable: Mapped[str] = mapped_column(String(100), index=True)
    verdict: Mapped[str] = mapped_column(String(50))
    coder_approach: Mapped[str] = mapped_column(String(200))
    qc_approach: Mapped[str] = mapped_column(String(200))
    study: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkflowStateRow(Base):
    __tablename__ = "workflow_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    state_json: Mapped[str] = mapped_column(Text)
    fsm_state: Mapped[str] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
