"""Business configuration and FAQs routes."""

from datetime import datetime
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo

from backend.app.db import get_db
from backend.app.models.business import (
    Business,
    BusinessDetailResponse,
    BusinessUpdate,
    TablesSummary,
)

from backend.app.utils.time import now_utc

router = APIRouter(prefix="/businesses", tags=["Businesses"])


@router.get("/{business_id}", response_model=BusinessDetailResponse)
async def get_business(
    business_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> BusinessDetailResponse:
    """Retrieve business configuration, operating hours, FAQs, and table summary."""
    business = await db["businesses"].find_one(
        {"$or": [{"id": business_id}, {"_id": business_id}]}
    )
    if not business:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "BUSINESS_NOT_FOUND",
                "message": f"Business with ID '{business_id}' does not exist.",
            },
        )

    # Tables summary
    tables_cursor = db["tables"].find({"business_id": business_id, "is_active": True}).sort(
        "table_number", pymongo.ASCENDING
    )
    tables = await tables_cursor.to_list(length=100)

    total_tables = len(tables)
    max_capacity = max((t["capacity"] for t in tables), default=0)
    capacities = sorted(list({t["capacity"] for t in tables}))

    sanitized_tables = [
        {
            "id": t.get("id") or str(t.get("_id")),
            "table_number": t["table_number"],
            "capacity": t["capacity"],
            "is_active": t.get("is_active", True),
        }
        for t in tables
    ]

    summary = TablesSummary(
        total_tables=total_tables,
        max_capacity=max_capacity,
        capacities=capacities,
        tables=sanitized_tables,
    )

    # Normalize business document
    biz_id = business.get("id") or str(business.get("_id"))
    biz_obj = Business(
        id=biz_id,
        name=business["name"],
        phone_number=business.get("phone_number", ""),
        timezone=business.get("timezone", "Asia/Kolkata"),
        opening_hours=business.get("opening_hours", {}),
        faqs=business.get("faqs", []),
        menu_summary=business.get("menu_summary", ""),
        slot_minutes=int(business.get("slot_minutes", 60)),
        booking_policy=business.get("booking_policy", ""),
        created_at=business.get("created_at", now_utc()),
        updated_at=business.get("updated_at", now_utc()),
    )

    return BusinessDetailResponse(business=biz_obj, tables_summary=summary)


@router.put("/{business_id}", response_model=Business)
async def update_business(
    business_id: str,
    payload: BusinessUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> Business:
    """Update business details such as opening hours, FAQs, slot duration."""
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=400,
            detail={"error": "NO_UPDATES_PROVIDED", "message": "No valid fields provided for update."},
        )

    update_data["updated_at"] = now_utc()

    result = await db["businesses"].find_one_and_update(
        {"$or": [{"id": business_id}, {"_id": business_id}]},
        {"$set": update_data},
        return_document=pymongo.ReturnDocument.AFTER,
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "BUSINESS_NOT_FOUND",
                "message": f"Business with ID '{business_id}' does not exist.",
            },
        )

    return Business(
        id=result.get("id") or str(result.get("_id")),
        name=result["name"],
        phone_number=result.get("phone_number", ""),
        timezone=result.get("timezone", "Asia/Kolkata"),
        opening_hours=result.get("opening_hours", {}),
        faqs=result.get("faqs", []),
        menu_summary=result.get("menu_summary", ""),
        slot_minutes=int(result.get("slot_minutes", 60)),
        booking_policy=result.get("booking_policy", ""),
        created_at=result.get("created_at", now_utc()),
        updated_at=result.get("updated_at", now_utc()),
    )
