"""Reservation management routes."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo

from backend.app.db import get_db
from backend.app.models.booking import (
    BookingCancelByPhoneRequest,
    BookingCreateRequest,
    BookingResponse,
    BookingStatus,
)
from backend.app.services.booking_service import (
    cancel_booking_by_id,
    cancel_booking_by_phone,
    create_booking,
    normalize_phone,
)

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def make_booking(
    request: BookingCreateRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> BookingResponse:
    """Create a new table reservation with automated table assignment and conflict resolution."""
    return await create_booking(db=db, request=request)


@router.get("", response_model=List[BookingResponse])
async def list_bookings(
    business_id: str = Query(..., description="Filter by business ID"),
    date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Filter by date YYYY-MM-DD"),
    status: Optional[BookingStatus] = Query(None, description="Filter by status (confirmed/cancelled)"),
    customer_phone: Optional[str] = Query(None, description="Filter by customer phone"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> List[BookingResponse]:
    """Retrieve reservations filtered by business, date, status, and phone."""
    query: dict = {"business_id": business_id}

    if date:
        query["date"] = date
    if status:
        query["status"] = status.value
    if customer_phone:
        query["customer_phone"] = normalize_phone(customer_phone)

    cursor = db["bookings"].find(query).sort("slot_start", pymongo.ASCENDING).limit(limit)
    records = await cursor.to_list(length=limit)

    return [
        BookingResponse(
            id=r["id"],
            business_id=r["business_id"],
            table_id=r["table_id"],
            table_number=r["table_number"],
            customer_name=r["customer_name"],
            customer_phone=r["customer_phone"],
            party_size=r["party_size"],
            date=r["date"],
            time=r["time"],
            slot_start=r["slot_start"],
            slot_end=r["slot_end"],
            status=BookingStatus(r["status"]),
            call_id=r.get("call_id"),
            created_at=r["created_at"],
            cancelled_at=r.get("cancelled_at"),
        )
        for r in records
    ]


@router.patch("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> BookingResponse:
    """Cancel a booking by its unique ID, freeing the table slot."""
    return await cancel_booking_by_id(db=db, booking_id=booking_id)


@router.post("/cancel-by-phone", response_model=BookingResponse)
async def cancel_by_phone(
    request: BookingCancelByPhoneRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> BookingResponse:
    """Cancel a booking by matching customer phone, date, and slot time (used by LLM voice tool)."""
    return await cancel_booking_by_phone(db=db, request=request)
