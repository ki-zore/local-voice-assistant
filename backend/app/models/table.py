"""Restaurant Table models."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class Table(BaseModel):
    """Restaurant dining table."""

    id: str = Field(..., description="Unique table ID")
    business_id: str
    table_number: int
    capacity: int = Field(..., ge=1, description="Seating capacity of the table")
    is_active: bool = True

    model_config = ConfigDict(populate_by_name=True)


class TableCreate(BaseModel):
    """Request schema for creating a new table."""

    table_number: int = Field(..., ge=1)
    capacity: int = Field(..., ge=1)
    is_active: bool = True
