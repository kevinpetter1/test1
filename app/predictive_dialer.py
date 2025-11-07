from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from sqlalchemy.orm import Session

from . import crud
from .models import Lead, LeadStatus


@dataclass
class DialerDecision:
    leads_to_dial: List[Lead]
    dial_now: bool
    reason: str


class PredictiveDialer:
    """Simple predictive dialer that balances agent availability and abandon rate."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _count_active_calls(self, campaign_id: int) -> int:
        return sum(
            1
            for lead in crud.list_leads(
                self.db, campaign_id=campaign_id, status=LeadStatus.IN_PROGRESS
            )
        )

    def decide(
        self,
        *,
        campaign_id: int,
        available_capacity: int,
        leads_queue: Iterable[Lead],
        max_parallel_calls: int,
    ) -> DialerDecision:
        leads_list = list(leads_queue)
        active_calls = self._count_active_calls(campaign_id)
        if not leads_list:
            return DialerDecision([], False, "No leads available")

        if available_capacity <= 0:
            return DialerDecision([], False, "No agent capacity")

        target_outbound = min(max_parallel_calls - active_calls, len(leads_list))
        if target_outbound <= 0:
            return DialerDecision([], False, "Parallel call limit reached")
        if available_capacity > 0:
            target_outbound = min(target_outbound, max(1, available_capacity * 2))

        leads_to_dial = leads_list[: max(1, target_outbound)]
        reason = "Dialing {} leads".format(len(leads_to_dial))
        return DialerDecision(leads_to_dial, True, reason)

    def assign_and_mark(self, leads: Iterable[Lead]) -> None:
        for lead in leads:
            crud.mark_lead_in_progress(self.db, lead.id)
