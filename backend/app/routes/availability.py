"""Availability route."""

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.app.db import get_db
from backend.app.models.booking import AvailabilityRequest, AvailabilityResponse
from backend.app.services.booking_service import check_availability

router = APIRouter(tags=["Availability"])


@router.post("/availability", response_model=AvailabilityResponse)
async def get_availability(
    request: AvailabilityRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> AvailabilityResponse:
    """Check table availability for a specific date and party size, optionally checking a specific time."""
    return await check_availability(
        db=db,
        business_id=request.business_id,
        date_str=request.date,
        time_str=request.time,
        party_size=request.party_size,
    )
