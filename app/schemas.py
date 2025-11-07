from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .models import CallOutcome, LeadStatus


class AgentBase(BaseModel):
    name: str
    extension: str
    is_available: bool = True
    max_concurrent_calls: int = Field(ge=1, default=1)


class AgentCreate(AgentBase):
    campaign_id: int


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    is_available: Optional[bool] = None
    max_concurrent_calls: Optional[int] = Field(default=None, ge=1)


class Agent(AgentBase):
    id: int
    campaign_id: int
    created_at: datetime

    class Config:
        orm_mode = True


class LeadBase(BaseModel):
    phone_number: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    details: Optional[str] = None
    priority: int = 0


class LeadCreate(LeadBase):
    campaign_id: int


class LeadUpdate(BaseModel):
    phone_number: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    details: Optional[str] = None
    priority: Optional[int] = None
    status: Optional[LeadStatus] = None


class Lead(LeadBase):
    id: int
    status: LeadStatus
    campaign_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class CampaignBase(BaseModel):
    name: str
    description: Optional[str] = None
    target_service_level: int = Field(ge=0, le=100, default=80)
    max_abandon_rate: int = Field(ge=0, le=100, default=5)


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    description: Optional[str] = None
    is_active: Optional[bool] = None
    target_service_level: Optional[int] = Field(default=None, ge=0, le=100)
    max_abandon_rate: Optional[int] = Field(default=None, ge=0, le=100)


class Campaign(CampaignBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True


class CallAttempt(BaseModel):
    id: int
    lead_id: int
    campaign_id: int
    agent_id: Optional[int]
    telnyx_call_control_id: Optional[str]
    telnyx_call_session_id: Optional[str]
    outcome: Optional[CallOutcome]
    dialed_at: datetime
    completed_at: Optional[datetime]
    notes: Optional[str]

    class Config:
        orm_mode = True


class PredictiveDialerConfig(BaseModel):
    campaign_id: int
    target_abandon_rate: int = Field(ge=0, le=100, default=5)
    target_service_level: int = Field(ge=0, le=100, default=80)


class DialerStartRequest(BaseModel):
    campaign_id: int
    max_parallel_calls: int = Field(ge=1, le=25, default=3)
    poll_interval_seconds: int = Field(ge=1, le=60, default=5)


class DialerStopRequest(BaseModel):
    campaign_id: int


class TelnyxCallRequest(BaseModel):
    to: str
    from_number: str = Field(alias="from")
    connection_id: str
    webhook_url: str
    timeout_secs: int = Field(default=45, ge=5, le=120)


class TelnyxWebhookEvent(BaseModel):
    data: dict


class LeadListResponse(BaseModel):
    total: int
    items: List[Lead]


class CampaignSummary(BaseModel):
    campaign: Campaign
    total_leads: int
    leads_by_status: Dict[LeadStatus, int]
    total_agents: int
    available_agents: int
    active_calls: int
    completed_calls: int
