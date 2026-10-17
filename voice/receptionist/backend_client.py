"""Async HTTP client for calling the FastAPI backend API."""

from datetime import datetime
import logging
from typing import Any, Dict, Optional
import httpx

from voice.receptionist.config import get_voice_config

logger = logging.getLogger("voice_assistant.backend_client")


class BackendClient:
    """Asynchronous client interacting with the Phase 1 backend."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        config = get_voice_config()
        self.base_url = (base_url or config.backend_url).rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        await self.client.aclose()

    async def get_business(self, business_id: str) -> Dict[str, Any]:
        """Fetch business configuration, operating hours, and FAQs."""
        resp = await self.client.get(f"/businesses/{business_id}")
        resp.raise_for_status()
        return resp.json()

    async def check_availability(
        self,
        business_id: str,
        date: str,
        party_size: int,
        time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check open table slots for a given date, party size, and optional time."""
        payload: Dict[str, Any] = {
            "business_id": business_id,
            "date": date,
            "party_size": party_size,
        }
        if time:
            payload["time"] = time

        resp = await self.client.post("/availability", json=payload)
        return resp.json()

    async def book_table(
        self,
        business_id: str,
        customer_name: str,
        customer_phone: str,
        party_size: int,
        date: str,
        time: str,
        call_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Attempt to book a table reservation."""
        payload = {
            "business_id": business_id,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "party_size": party_size,
            "date": date,
            "time": time,
            "call_id": call_id,
        }
        resp = await self.client.post("/bookings", json=payload)
        return resp.json()

    async def cancel_booking(
        self,
        business_id: str,
        customer_phone: str,
        date: str,
        time: str,
    ) -> Dict[str, Any]:
        """Cancel an existing booking using customer phone, date, and slot time."""
        payload = {
            "business_id": business_id,
            "customer_phone": customer_phone,
            "date": date,
            "time": time,
        }
        resp = await self.client.post("/bookings/cancel-by-phone", json=payload)
        return resp.json()

    async def create_call(self, business_id: str) -> Dict[str, Any]:
        """Register the start of a voice call session."""
        payload = {"business_id": business_id}
        resp = await self.client.post("/calls", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def update_call(
        self,
        call_id: str,
        outcome: Optional[str] = None,
        ended_at: Optional[datetime] = None,
        transcript_item: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update a call's status, append transcript, or record outcome."""
        payload: Dict[str, Any] = {}
        if outcome:
            payload["outcome"] = outcome
        if ended_at:
            payload["ended_at"] = ended_at.isoformat()
        if transcript_item:
            payload["transcript_item"] = transcript_item

        resp = await self.client.patch(f"/calls/{call_id}", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def log_unanswered_question(
        self,
        call_id: str,
        question: str,
    ) -> Dict[str, Any]:
        """Log an unanswered question for manager triage."""
        payload = {"question": question}
        resp = await self.client.post(f"/calls/{call_id}/unanswered", json=payload)
        resp.raise_for_status()
        return resp.json()
