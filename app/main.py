from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from typing import Dict, List, Sequence

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import crud
from .database import Base, SessionLocal, engine
from .dependencies import get_db, get_telnyx_api_key
from .models import CallOutcome, LeadStatus
from .predictive_dialer import PredictiveDialer
from .schemas import (
    Agent,
    AgentCreate,
    AgentUpdate,
    CallAttempt as CallAttemptSchema,
    Campaign,
    CampaignCreate,
    CampaignSummary,
    CampaignUpdate,
    DialerStartRequest,
    DialerStopRequest,
    Lead,
    LeadCreate,
    LeadListResponse,
    LeadUpdate,
    TelnyxWebhookEvent,
)
from .telnyx_client import TelnyxClient

load_dotenv()

logger = logging.getLogger(__name__)

_running_dialers: Dict[int, asyncio.Task] = {}

app = FastAPI(title="Predictive Dialer", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.post("/campaigns", response_model=Campaign)
def create_campaign(
    payload: CampaignCreate, db=Depends(get_db)
):
    return crud.create_campaign(db, payload)


@app.get("/campaigns", response_model=List[Campaign])
def list_campaigns(db=Depends(get_db)):
    return crud.list_campaigns(db)


@app.patch("/campaigns/{campaign_id}", response_model=Campaign)
def update_campaign(campaign_id: int, payload: CampaignUpdate, db=Depends(get_db)):
    campaign = crud.update_campaign(db, campaign_id, payload)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@app.get("/campaigns/{campaign_id}/summary", response_model=CampaignSummary)
def campaign_summary(campaign_id: int, db=Depends(get_db)):
    summary = crud.get_campaign_summary(db, campaign_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return summary


@app.post("/leads", response_model=Lead)
def create_lead(payload: LeadCreate, db=Depends(get_db)):
    return crud.create_lead(db, payload)


@app.post("/leads/bulk", response_model=LeadListResponse)
def bulk_create_leads(leads: List[LeadCreate], db=Depends(get_db)):
    created = crud.bulk_create_leads(db, leads)
    return LeadListResponse(total=len(created), items=list(created))


@app.get("/leads", response_model=LeadListResponse)
def list_leads(
    campaign_id: int | None = None,
    status: LeadStatus | None = None,
    skip: int = 0,
    limit: int = 100,
    db=Depends(get_db),
):
    items = crud.list_leads(db, campaign_id=campaign_id, status=status, skip=skip, limit=limit)
    total = crud.count_leads(db, campaign_id=campaign_id, status=status)
    return LeadListResponse(total=total, items=list(items))


@app.patch("/leads/{lead_id}", response_model=Lead)
def update_lead(lead_id: int, payload: LeadUpdate, db=Depends(get_db)):
    lead = crud.update_lead(db, lead_id, payload)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@app.delete("/leads/{lead_id}", status_code=204)
def delete_lead(lead_id: int, db=Depends(get_db)):
    if not crud.delete_lead(db, lead_id):
        raise HTTPException(status_code=404, detail="Lead not found")
    return None


@app.post("/agents", response_model=Agent)
def create_agent(payload: AgentCreate, db=Depends(get_db)):
    return crud.create_agent(db, payload)


@app.get("/agents", response_model=List[Agent])
def list_agents(campaign_id: int | None = None, db=Depends(get_db)):
    return list(crud.list_agents(db, campaign_id=campaign_id))


@app.patch("/agents/{agent_id}", response_model=Agent)
def update_agent(agent_id: int, payload: AgentUpdate, db=Depends(get_db)):
    agent = crud.update_agent(db, agent_id, payload)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def _dial_leads(*, dialer_request: DialerStartRequest, api_key: str) -> None:
    logger.info("Dialer started for campaign %s", dialer_request.campaign_id)
    db_session = SessionLocal()
    telnyx_client = TelnyxClient(api_key)
    dialer = PredictiveDialer(db_session)
    poll_interval = max(1, dialer_request.poll_interval_seconds)
    try:
        while True:
            leads_queue: Sequence[Lead] = crud.list_leads(
                db_session, campaign_id=dialer_request.campaign_id, status=LeadStatus.NEW
            )
            agent_slots = crud.get_agent_capacity_slots(db_session, dialer_request.campaign_id)
            decision = dialer.decide(
                campaign_id=dialer_request.campaign_id,
                available_capacity=len(agent_slots),
                leads_queue=leads_queue,
                max_parallel_calls=dialer_request.max_parallel_calls,
            )
            if not decision.dial_now:
                logger.debug(
                    "Dialer waiting for campaign %s: %s",
                    dialer_request.campaign_id,
                    decision.reason,
                )
                if decision.reason == "No leads available":
                    logger.info(
                        "Dialer finished for campaign %s", dialer_request.campaign_id
                    )
                    break
                await asyncio.sleep(poll_interval)
                continue

            outbound_number = os.getenv("TELNYX_OUTBOUND_NUMBER")
            connection_id = os.getenv("TELNYX_CONNECTION_ID")
            if not outbound_number or not connection_id:
                logger.error("Telnyx connection settings missing; cannot place calls")
                break

            webhook_url = os.getenv("TELNYX_WEBHOOK_URL", "")
            if not webhook_url:
                logger.warning("TELNYX_WEBHOOK_URL is not configured; call events will fail")

            slots_queue = deque(agent_slots)
            for lead in decision.leads_to_dial:
                assigned_agent = slots_queue.popleft() if slots_queue else None
                dialer.assign_and_mark([lead])
                try:
                    response = await telnyx_client.create_call(
                        to=lead.phone_number,
                        from_number=outbound_number,
                        connection_id=connection_id,
                        webhook_url=webhook_url,
                    )
                except HTTPException:
                    logger.exception(
                        "Failed to originate call for lead %s in campaign %s",
                        lead.id,
                        dialer_request.campaign_id,
                    )
                    crud.update_lead(
                        db_session,
                        lead.id,
                        LeadUpdate(status=LeadStatus.NEW),
                    )
                    if assigned_agent:
                        slots_queue.appendleft(assigned_agent)
                    continue

                call_data = response.get("data", {})
                call_control_id = call_data.get("call_control_id")
                call_session_id = call_data.get("call_session_id")
                crud.create_call_attempt(
                    db_session,
                    campaign_id=dialer_request.campaign_id,
                    lead_id=lead.id,
                    agent_id=assigned_agent.id if assigned_agent else None,
                    telnyx_call_control_id=call_control_id,
                    telnyx_call_session_id=call_session_id,
                )
            await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        logger.info("Dialer task cancelled for campaign %s", dialer_request.campaign_id)
        raise
    finally:
        await telnyx_client.close()
        db_session.close()


@app.post("/dialer/start")
async def start_dialer(
    payload: DialerStartRequest,
    api_key: str = Depends(get_telnyx_api_key),
):
    existing_task = _running_dialers.get(payload.campaign_id)
    if existing_task and not existing_task.done():
        raise HTTPException(status_code=409, detail="Dialer already running for this campaign")

    task = asyncio.create_task(
        _dial_leads(dialer_request=payload, api_key=api_key),
        name=f"dialer-{payload.campaign_id}",
    )

    def _cleanup(fut: asyncio.Task) -> None:
        _running_dialers.pop(payload.campaign_id, None)
        try:
            fut.result()
        except asyncio.CancelledError:
            logger.debug("Dialer task for campaign %s cancelled", payload.campaign_id)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception(
                "Dialer task for campaign %s exited with error", payload.campaign_id
            )

    task.add_done_callback(_cleanup)
    _running_dialers[payload.campaign_id] = task
    return {"detail": "Dialer started"}


@app.post("/dialer/stop")
async def stop_dialer(payload: DialerStopRequest):
    task = _running_dialers.get(payload.campaign_id)
    if not task or task.done():
        raise HTTPException(status_code=404, detail="No active dialer for this campaign")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return {"detail": "Dialer stopped"}


@app.get("/dialer/status/{campaign_id}")
async def dialer_status(campaign_id: int):
    task = _running_dialers.get(campaign_id)
    running = bool(task and not task.done())
    return {"campaign_id": campaign_id, "running": running}


@app.post("/webhooks/telnyx")
async def telnyx_webhook(event: TelnyxWebhookEvent, db=Depends(get_db)):
    payload = event.data
    event_type = payload.get("event_type")
    call_control_id = payload.get("payload", {}).get("call_control_id")
    if not call_control_id:
        logger.warning("Webhook without call_control_id: %s", payload)
        return {"detail": "ignored"}

    outcome = _map_event_to_outcome(event_type)
    call_attempt = crud.update_call_attempt_outcome(
        db, call_control_id, outcome=outcome, notes=event_type
    )
    if call_attempt:
        if call_attempt.agent_id:
            crud.set_agent_availability(db, call_attempt.agent_id, is_available=True)
        if outcome in {CallOutcome.ANSWERED, CallOutcome.TRANSFERRED}:
            crud.mark_lead_completed(db, call_attempt.lead_id)
        else:
            crud.update_lead(db, call_attempt.lead_id, LeadUpdate(status=LeadStatus.NEW))
    return {"detail": "ok"}


@app.get("/call-attempts", response_model=List[CallAttemptSchema])
def list_call_attempts(
    campaign_id: int | None = None,
    lead_id: int | None = None,
    active_only: bool = False,
    skip: int = 0,
    limit: int = 100,
    db=Depends(get_db),
):
    attempts = crud.list_call_attempts(
        db,
        campaign_id=campaign_id,
        lead_id=lead_id,
        active_only=active_only,
        skip=skip,
        limit=limit,
    )
    return list(attempts)


def _map_event_to_outcome(event_type: str | None) -> CallOutcome:
    mapping = {
        "call.answered": CallOutcome.ANSWERED,
        "call.no_answer": CallOutcome.NO_ANSWER,
        "call.hangup": CallOutcome.TRANSFERRED,
        "call.failed": CallOutcome.FAILED,
        "call.busy": CallOutcome.BUSY,
    }
    return mapping.get(event_type, CallOutcome.FAILED)
