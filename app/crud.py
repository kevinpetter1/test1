from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from . import models
from .models import Agent, Campaign, CallAttempt, CallOutcome, Lead, LeadStatus
from .schemas import AgentCreate, AgentUpdate, CampaignCreate, CampaignUpdate, LeadCreate, LeadUpdate


def create_campaign(db: Session, campaign: CampaignCreate) -> Campaign:
    db_campaign = Campaign(**campaign.dict())
    db.add(db_campaign)
    db.commit()
    db.refresh(db_campaign)
    return db_campaign


def update_campaign(db: Session, campaign_id: int, payload: CampaignUpdate) -> Optional[Campaign]:
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        return None
    for key, value in payload.dict(exclude_unset=True).items():
        setattr(campaign, key, value)
    db.commit()
    db.refresh(campaign)
    return campaign


def list_campaigns(db: Session) -> List[Campaign]:
    return db.execute(select(Campaign).order_by(Campaign.created_at.desc())).scalars().all()


def get_campaign(db: Session, campaign_id: int) -> Optional[Campaign]:
    return db.get(Campaign, campaign_id)


def create_lead(db: Session, lead: LeadCreate) -> Lead:
    db_lead = Lead(**lead.dict())
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)
    return db_lead


def bulk_create_leads(db: Session, leads: Iterable[LeadCreate]) -> Sequence[Lead]:
    payload = [Lead(**lead.dict()) for lead in leads]
    db.add_all(payload)
    db.commit()
    for lead in payload:
        db.refresh(lead)
    return payload


def update_lead(db: Session, lead_id: int, payload: LeadUpdate) -> Optional[Lead]:
    lead = db.get(Lead, lead_id)
    if not lead:
        return None
    for key, value in payload.dict(exclude_unset=True).items():
        setattr(lead, key, value)
    db.commit()
    db.refresh(lead)
    return lead


def delete_lead(db: Session, lead_id: int) -> bool:
    lead = db.get(Lead, lead_id)
    if not lead:
        return False
    db.delete(lead)
    db.commit()
    return True


def list_leads(
    db: Session,
    campaign_id: Optional[int] = None,
    status: Optional[LeadStatus] = None,
    skip: int = 0,
    limit: int = 100,
) -> Sequence[Lead]:
    stmt = select(Lead)
    if campaign_id is not None:
        stmt = stmt.where(Lead.campaign_id == campaign_id)
    if status is not None:
        stmt = stmt.where(Lead.status == status)
    stmt = stmt.order_by(desc(Lead.priority), asc(Lead.created_at)).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()


def count_leads(db: Session, campaign_id: Optional[int] = None, status: Optional[LeadStatus] = None) -> int:
    stmt = select(func.count(Lead.id))
    if campaign_id is not None:
        stmt = stmt.where(Lead.campaign_id == campaign_id)
    if status is not None:
        stmt = stmt.where(Lead.status == status)
    return db.execute(stmt).scalar_one()


def create_agent(db: Session, payload: AgentCreate) -> Agent:
    agent = Agent(**payload.dict())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def update_agent(db: Session, agent_id: int, payload: AgentUpdate) -> Optional[Agent]:
    agent = db.get(Agent, agent_id)
    if not agent:
        return None
    for key, value in payload.dict(exclude_unset=True).items():
        setattr(agent, key, value)
    db.commit()
    db.refresh(agent)
    return agent


def list_agents(db: Session, campaign_id: Optional[int] = None) -> Sequence[Agent]:
    stmt = select(Agent)
    if campaign_id is not None:
        stmt = stmt.where(Agent.campaign_id == campaign_id)
    stmt = stmt.order_by(Agent.created_at.desc())
    return db.execute(stmt).scalars().all()


def get_available_agents(db: Session, campaign_id: int) -> Sequence[Agent]:
    stmt = select(Agent).where(Agent.campaign_id == campaign_id, Agent.is_available.is_(True))
    return db.execute(stmt).scalars().all()


def count_active_calls_for_agent(db: Session, agent_id: int) -> int:
    stmt = select(func.count(CallAttempt.id)).where(
        CallAttempt.agent_id == agent_id, CallAttempt.outcome.is_(None)
    )
    return db.execute(stmt).scalar_one()


def get_agent_capacity_slots(db: Session, campaign_id: int) -> List[Agent]:
    """Return a list of agents repeated for each open dialing slot."""

    agents = list_agents(db, campaign_id=campaign_id)
    available_slots: List[Agent] = []
    for agent in agents:
        if not agent.is_available:
            continue
        active_calls = count_active_calls_for_agent(db, agent.id)
        remaining_capacity = max(agent.max_concurrent_calls - active_calls, 0)
        if remaining_capacity <= 0:
            continue
        available_slots.extend([agent] * remaining_capacity)
    return available_slots


def set_agent_availability(db: Session, agent_id: int, *, is_available: bool) -> Optional[Agent]:
    agent = db.get(Agent, agent_id)
    if not agent:
        return None
    agent.is_available = is_available
    db.commit()
    db.refresh(agent)
    return agent


def create_call_attempt(
    db: Session,
    *,
    campaign_id: int,
    lead_id: int,
    agent_id: Optional[int],
    telnyx_call_control_id: Optional[str] = None,
    telnyx_call_session_id: Optional[str] = None,
) -> CallAttempt:
    call_attempt = CallAttempt(
        campaign_id=campaign_id,
        lead_id=lead_id,
        agent_id=agent_id,
        telnyx_call_control_id=telnyx_call_control_id,
        telnyx_call_session_id=telnyx_call_session_id,
    )
    db.add(call_attempt)
    db.commit()
    db.refresh(call_attempt)
    return call_attempt


def update_call_attempt_outcome(
    db: Session,
    call_control_id: str,
    *,
    outcome: CallOutcome,
    notes: Optional[str] = None,
) -> Optional[CallAttempt]:
    stmt = select(CallAttempt).where(CallAttempt.telnyx_call_control_id == call_control_id)
    call_attempt = db.execute(stmt).scalar_one_or_none()
    if not call_attempt:
        return None
    call_attempt.outcome = outcome
    call_attempt.completed_at = datetime.utcnow()
    call_attempt.notes = notes
    db.commit()
    db.refresh(call_attempt)
    return call_attempt


def list_call_attempts(
    db: Session,
    *,
    campaign_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    active_only: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> Sequence[CallAttempt]:
    stmt = select(CallAttempt)
    if campaign_id is not None:
        stmt = stmt.where(CallAttempt.campaign_id == campaign_id)
    if lead_id is not None:
        stmt = stmt.where(CallAttempt.lead_id == lead_id)
    if active_only:
        stmt = stmt.where(CallAttempt.outcome.is_(None))
    stmt = stmt.order_by(desc(CallAttempt.dialed_at)).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()


def get_campaign_summary(db: Session, campaign_id: int) -> Optional[Dict[str, object]]:
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        return None

    total_leads = count_leads(db, campaign_id=campaign_id)
    status_counts: Dict[LeadStatus, int] = {status: 0 for status in LeadStatus}
    status_rows = db.execute(
        select(Lead.status, func.count(Lead.id))
        .where(Lead.campaign_id == campaign_id)
        .group_by(Lead.status)
    ).all()
    for status, count in status_rows:
        status_counts[status] = count

    total_agents = db.execute(
        select(func.count(Agent.id)).where(Agent.campaign_id == campaign_id)
    ).scalar_one()
    available_agents = db.execute(
        select(func.count(Agent.id)).where(
            Agent.campaign_id == campaign_id, Agent.is_available.is_(True)
        )
    ).scalar_one()

    active_calls = db.execute(
        select(func.count(CallAttempt.id)).where(
            CallAttempt.campaign_id == campaign_id,
            CallAttempt.outcome.is_(None),
        )
    ).scalar_one()
    completed_calls = db.execute(
        select(func.count(CallAttempt.id)).where(
            CallAttempt.campaign_id == campaign_id,
            CallAttempt.outcome.isnot(None),
        )
    ).scalar_one()

    return {
        "campaign": campaign,
        "total_leads": total_leads,
        "leads_by_status": status_counts,
        "total_agents": total_agents,
        "available_agents": available_agents,
        "active_calls": active_calls,
        "completed_calls": completed_calls,
    }


def mark_lead_in_progress(db: Session, lead_id: int) -> Optional[Lead]:
    lead = db.get(Lead, lead_id)
    if not lead:
        return None
    lead.status = LeadStatus.IN_PROGRESS
    db.commit()
    db.refresh(lead)
    return lead


def mark_lead_completed(db: Session, lead_id: int) -> Optional[Lead]:
    lead = db.get(Lead, lead_id)
    if not lead:
        return None
    lead.status = LeadStatus.COMPLETED
    db.commit()
    db.refresh(lead)
    return lead
