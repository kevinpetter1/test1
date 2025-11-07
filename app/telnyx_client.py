from __future__ import annotations

import logging
from typing import Any, Dict

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class TelnyxClient:
    BASE_URL = "https://api.telnyx.com/v2"

    def __init__(self, api_key: str, *, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=timeout,
        )

    async def create_call(
        self,
        *,
        to: str,
        from_number: str,
        connection_id: str,
        webhook_url: str,
        timeout_secs: int = 45,
    ) -> Dict[str, Any]:
        payload = {
            "to": to,
            "from": from_number,
            "connection_id": connection_id,
            "timeout_secs": timeout_secs,
        }
        if webhook_url:
            payload["webhook_url"] = webhook_url
        response = await self._client.post("/calls", json=payload)
        if response.status_code >= 400:
            logger.error("Telnyx create call failed: %s", response.text)
            raise HTTPException(status_code=502, detail="Telnyx create call failed")
        return response.json()

    async def hangup_call(self, call_control_id: str) -> Dict[str, Any]:
        response = await self._client.post(f"/calls/{call_control_id}/actions/hangup")
        if response.status_code >= 400:
            logger.error("Telnyx hangup failed: %s", response.text)
            raise HTTPException(status_code=502, detail="Telnyx hangup failed")
        return response.json()

    async def close(self) -> None:
        await self._client.aclose()


async def get_telnyx_client(api_key: str) -> TelnyxClient:
    return TelnyxClient(api_key)
