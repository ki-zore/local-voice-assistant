"""Business and operating hours Pydantic models."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


from backend.app.utils.time import now_utc


class TimeRange(BaseModel):
    """Opening and closing time for a single day (24-hour HH:MM format)."""

    open: str = Field(..., pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$", description="Open time HH:MM")
    close: str = Field(..., pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$", description="Close time HH:MM")


class FAQItem(BaseModel):
    """Business FAQ entry."""

    question: str
    answer: str


class Business(BaseModel):
    """Complete Business entity stored in MongoDB."""

    id: str = Field(..., description="Unique business identifier (e.g. cafe_demo_001)")
    name: str
    phone_number: str
    timezone: str = "Asia/Kolkata"
    opening_hours: Dict[str, Optional[TimeRange]] = Field(
        default_factory=dict,
        description="Keys are lowercase weekdays ('monday', 'tuesday', etc.). None indicates closed.",
    )
    faqs: List[FAQItem] = Field(default_factory=list)
    menu_summary: str = ""
    slot_minutes: int = 60
    booking_policy: str = ""
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    model_config = ConfigDict(populate_by_name=True)


class BusinessUpdate(BaseModel):
    """Fields that can be updated via PUT /businesses/{id}."""

    name: Optional[str] = None
    phone_number: Optional[str] = None
    timezone: Optional[str] = None
    opening_hours: Optional[Dict[str, Optional[TimeRange]]] = None
    faqs: Optional[List[FAQItem]] = None
    menu_summary: Optional[str] = None
    slot_minutes: Optional[int] = Field(None, ge=15, le=1440)
    booking_policy: Optional[str] = None


class TablesSummary(BaseModel):
    """Summary of tables for the business."""

    total_tables: int
    max_capacity: int
    capacities: List[int]
    tables: List[Dict[str, Any]] = Field(default_factory=list)


class BusinessDetailResponse(BaseModel):
    """Response model for GET /businesses/{id}."""

    business: Business
    tables_summary: TablesSummary
