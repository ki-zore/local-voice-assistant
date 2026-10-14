"""Reservation and Availability Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class BookingStatus(str, Enum):
    """Booking confirmation status."""

    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class AvailabilityRequest(BaseModel):
    """Request payload for checking availability."""

    business_id: str = Field(..., description="Business ID")
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date in YYYY-MM-DD")
    time: Optional[str] = Field(None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$", description="Time in HH:MM")
    party_size: int = Field(..., ge=1, description="Number of guests")


class AvailabilityResponse(BaseModel):
    """Response payload for availability check."""

    business_id: str
    date: str
    time: Optional[str] = None
    party_size: int
    is_available: Optional[bool] = None
    open_slots: List[str] = Field(default_factory=list)
    alternative_slots: List[str] = Field(default_factory=list)
    message: str


class BookingCreateRequest(BaseModel):
    """Request payload for booking a table."""

    business_id: str
    customer_name: str = Field(..., min_length=2, description="Customer name")
    customer_phone: str = Field(..., min_length=6, description="Customer telephone number")
    party_size: int = Field(..., ge=1, description="Party size")
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date YYYY-MM-DD")
    time: str = Field(..., pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$", description="Time HH:MM")
    call_id: Optional[str] = Field(None, description="Linked phone call ID if booked via voice")


class BookingCancelByPhoneRequest(BaseModel):
    """Request payload for cancelling a booking by phone number and slot."""

    business_id: str
    customer_phone: str = Field(..., min_length=6)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(..., pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class BookingResponse(BaseModel):
    """Reservation details returned by API."""

    id: str
    business_id: str
    table_id: str
    table_number: int
    customer_name: str
    customer_phone: str
    party_size: int
    date: str
    time: str
    slot_start: datetime
    slot_end: datetime
    status: BookingStatus
    call_id: Optional[str] = None
    created_at: datetime
    cancelled_at: Optional[datetime] = None

    model_config = ConfigDict(populate_by_name=True)
