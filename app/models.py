from __future__ import annotations

import enum
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class LeadStatus(str, enum.Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DO_NOT_CALL = "do_not_call"


class CallOutcome(str, enum.Enum):
    ANSWERED = "answered"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    TRANSFERRED = "transferred"


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    target_service_level = Column(Integer, default=80, nullable=False)
    max_abandon_rate = Column(Integer, default=5, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    leads = relationship("Lead", back_populates="campaign", cascade="all, delete")
    agents = relationship("Agent", back_populates="campaign", cascade="all, delete")
    call_attempts = relationship("CallAttempt", back_populates="campaign")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    phone_number = Column(String(32), nullable=False, index=True)
    first_name = Column(String(128), nullable=True)
    last_name = Column(String(128), nullable=True)
    details = Column(Text, nullable=True)
    status = Column(Enum(LeadStatus), default=LeadStatus.NEW, nullable=False)
    priority = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    campaign = relationship("Campaign", back_populates="leads")
    call_attempts = relationship("CallAttempt", back_populates="lead")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    extension = Column(String(32), nullable=False, unique=True)
    is_available = Column(Boolean, default=True, nullable=False)
    max_concurrent_calls = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    campaign = relationship("Campaign", back_populates="agents")


class CallAttempt(Base):
    __tablename__ = "call_attempts"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    telnyx_call_control_id = Column(String(255), nullable=True, index=True)
    telnyx_call_session_id = Column(String(255), nullable=True)
    outcome = Column(Enum(CallOutcome), nullable=True)
    dialed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    campaign = relationship("Campaign", back_populates="call_attempts")
    lead = relationship("Lead", back_populates="call_attempts")
