"""Core booking logic, slot calculations, table assignment, and duplicate prevention."""

from datetime import datetime, timedelta
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo
from pymongo.errors import DuplicateKeyError

from backend.app.models.booking import (
    AvailabilityResponse,
    BookingCancelByPhoneRequest,
    BookingCreateRequest,
    BookingResponse,
    BookingStatus,
)
from backend.app.utils.time import (
    build_local_datetime,
    find_nearest_alternative_slots,
    generate_day_slots,
    is_slot_aligned,
    local_to_utc,
    now_in_tz,
    now_utc,
    parse_date_str,
    parse_time_str,
    utc_to_local,
)

logger = logging.getLogger("voice_assistant.booking_service")

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def normalize_phone(phone: str) -> str:
    """Normalize phone number: trim, remove whitespace and separators, retain optional leading +."""
    raw = phone.strip()
    has_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 6:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_PHONE",
                "message": "Please provide a valid phone number with at least 6 digits.",
            },
        )
    return f"+{digits}" if has_plus else digits


async def get_business_or_404(db: AsyncIOMotorDatabase, business_id: str) -> Dict[str, Any]:
    """Retrieve business record from database or raise 404."""
    business = await db["businesses"].find_one({"$or": [{"id": business_id}, {"_id": business_id}]})
    if not business:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "BUSINESS_NOT_FOUND",
                "message": f"Business with ID '{business_id}' does not exist.",
            },
        )
    return business


def validate_booking_datetime(
    business: Dict[str, Any],
    date_str: str,
    time_str: str,
    check_future: bool = True,
) -> Tuple[datetime, datetime, datetime, datetime]:
    """Validate requested date and time against business opening hours, timezone, and slot alignment.

    Returns:
        (local_start, local_end, slot_start_utc, slot_end_utc)
    """
    tz_name = business.get("timezone", "Asia/Kolkata")
    slot_minutes = int(business.get("slot_minutes", 60))

    try:
        date_val = parse_date_str(date_str)
        time_val = parse_time_str(time_str)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_DATETIME_FORMAT",
                "message": f"Invalid date or time format: {str(e)}",
            },
        )

    local_start = build_local_datetime(date_val, time_val, tz_name)
    slot_start_utc = local_to_utc(local_start)
    slot_end_local = local_start + timedelta(minutes=slot_minutes)
    slot_end_utc = local_to_utc(slot_end_local)

    # 1. Check if in the past
    if check_future:
        current_business_time = now_in_tz(tz_name)
        if local_start <= current_business_time:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "PAST_TIME",
                    "message": (
                        f"Cannot book a table in the past. Current business time is "
                        f"{current_business_time.strftime('%Y-%m-%d %H:%M')} ({tz_name})."
                    ),
                },
            )

    # 2. Check slot alignment
    if not is_slot_aligned(local_start, slot_minutes):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "SLOT_NOT_ALIGNED",
                "message": (
                    f"Requested time {time_str} must align with the {slot_minutes}-minute "
                    f"slot schedule (e.g., :00 on the hour)."
                ),
            },
        )

    # 3. Check day of week against business hours
    weekday_idx = date_val.weekday()
    weekday_name = WEEKDAYS[weekday_idx]
    opening_hours = business.get("opening_hours", {})
    day_schedule = opening_hours.get(weekday_name)

    if not day_schedule or not day_schedule.get("open") or not day_schedule.get("close"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "CLOSED_DAY",
                "message": f"The cafe is closed on {weekday_name.capitalize()}s.",
            },
        )

    open_str = day_schedule["open"]
    close_str = day_schedule["close"]
    open_time = parse_time_str(open_str)
    close_time = parse_time_str(close_str)

    req_time = local_start.time()

    # 4. Check if slot starts before open or at/after close
    if req_time < open_time or req_time >= close_time:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "OUTSIDE_HOURS",
                "message": (
                    f"The requested time {time_str} is outside operating hours "
                    f"({open_str} to {close_str} on {weekday_name.capitalize()})."
                ),
            },
        )

    # 5. Check if slot crosses closing time (slot must fully fit within hours)
    day_close_dt = build_local_datetime(date_val, close_time, tz_name)
    if slot_end_local > day_close_dt:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "SLOT_EXCEEDS_CLOSING",
                "message": (
                    f"A {slot_minutes}-minute reservation starting at {time_str} "
                    f"would exceed our closing time of {close_str}."
                ),
            },
        )

    return local_start, slot_end_local, slot_start_utc, slot_end_utc


async def get_candidate_tables(
    db: AsyncIOMotorDatabase,
    business_id: str,
    party_size: int,
) -> List[Dict[str, Any]]:
    """Fetch active tables that can seat party_size, ordered smallest capacity first.

    If party_size exceeds largest table capacity, raise 400.
    """
    if party_size < 1:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_PARTY_SIZE",
                "message": "Party size must be at least 1 guest.",
            },
        )

    all_tables_cursor = db["tables"].find(
        {"business_id": business_id, "is_active": True}
    ).sort([("capacity", pymongo.ASCENDING), ("table_number", pymongo.ASCENDING)])
    all_tables = await all_tables_cursor.to_list(length=100)

    if not all_tables:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "NO_TABLES_CONFIGURED",
                "message": "No active tables are configured for this business.",
            },
        )

    max_capacity = max(t["capacity"] for t in all_tables)
    if party_size > max_capacity:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "PARTY_TOO_LARGE",
                "message": (
                    f"Party size of {party_size} exceeds our maximum single-table "
                    f"capacity of {max_capacity} seats. Please call us directly for large groups."
                ),
            },
        )

    # Filter tables with capacity >= party_size (already sorted smallest capacity first)
    suitable = [t for t in all_tables if t["capacity"] >= party_size]
    return suitable


async def check_availability(
    db: AsyncIOMotorDatabase,
    business_id: str,
    date_str: str,
    time_str: Optional[str],
    party_size: int,
) -> AvailabilityResponse:
    """Check availability for open slots on a given date and optional time."""
    business = await get_business_or_404(db, business_id)
    tz_name = business.get("timezone", "Asia/Kolkata")
    slot_minutes = int(business.get("slot_minutes", 60))

    candidate_tables = await get_candidate_tables(db, business_id, party_size)
    candidate_ids = [t.get("id") or str(t.get("_id")) for t in candidate_tables]

    date_val = parse_date_str(date_str)
    weekday_name = WEEKDAYS[date_val.weekday()]
    opening_hours = business.get("opening_hours", {})
    day_schedule = opening_hours.get(weekday_name)

    if not day_schedule or not day_schedule.get("open") or not day_schedule.get("close"):
        return AvailabilityResponse(
            business_id=business_id,
            date=date_str,
            time=time_str,
            party_size=party_size,
            is_available=False,
            open_slots=[],
            alternative_slots=[],
            message=f"The cafe is closed on {weekday_name.capitalize()}s.",
        )

    all_possible_slots = generate_day_slots(
        day_schedule["open"], day_schedule["close"], slot_minutes
    )

    current_biz_time = now_in_tz(tz_name)
    open_slots: List[str] = []

    # Check each possible slot in the day
    for slot_time in all_possible_slots:
        local_slot_dt = build_local_datetime(date_val, parse_time_str(slot_time), tz_name)
        if local_slot_dt <= current_biz_time:
            # Past slot, cannot be booked
            continue

        slot_utc = local_to_utc(local_slot_dt)
        # Find confirmed bookings for candidate tables at this slot
        booked_count = await db["bookings"].count_documents(
            {
                "business_id": business_id,
                "table_id": {"$in": candidate_ids},
                "slot_start": slot_utc,
                "status": BookingStatus.CONFIRMED.value,
            }
        )

        if booked_count < len(candidate_ids):
            open_slots.append(slot_time)

    # Case 1: Specific time requested
    if time_str is not None:
        try:
            _, _, req_slot_utc, _ = validate_booking_datetime(
                business, date_str, time_str, check_future=True
            )
            is_requested_open = time_str in open_slots
        except HTTPException:
            is_requested_open = False

        if is_requested_open:
            return AvailabilityResponse(
                business_id=business_id,
                date=date_str,
                time=time_str,
                party_size=party_size,
                is_available=True,
                open_slots=open_slots,
                alternative_slots=[],
                message=f"A table for {party_size} is available at {time_str} on {date_str}.",
            )
        else:
            alternatives = find_nearest_alternative_slots(time_str, open_slots, max_count=3)
            return AvailabilityResponse(
                business_id=business_id,
                date=date_str,
                time=time_str,
                party_size=party_size,
                is_available=False,
                open_slots=open_slots,
                alternative_slots=alternatives,
                message=(
                    f"No tables are available for a party of {party_size} at {time_str} on {date_str}. "
                    + (
                        f"Nearest available times are: {', '.join(alternatives)}."
                        if alternatives
                        else "No other slots are open today."
                    )
                ),
            )

    # Case 2: Time omitted, return all open slots
    return AvailabilityResponse(
        business_id=business_id,
        date=date_str,
        time=None,
        party_size=party_size,
        is_available=len(open_slots) > 0,
        open_slots=open_slots,
        alternative_slots=[],
        message=(
            f"Found {len(open_slots)} available slot(s) for a party of {party_size} on {date_str}."
            if open_slots
            else f"No available slots for a party of {party_size} on {date_str}."
        ),
    )


async def create_booking(
    db: AsyncIOMotorDatabase,
    request: BookingCreateRequest,
) -> BookingResponse:
    """Create a table reservation, picking smallest fitting table and handling conflicts."""
    phone = normalize_phone(request.customer_phone)
    business = await get_business_or_404(db, request.business_id)

    # Validate slot, timezone, opening hours, future date
    local_start, local_end, slot_start_utc, slot_end_utc = validate_booking_datetime(
        business, request.date, request.time, check_future=True
    )

    # Get suitable tables sorted by capacity ASC, table_number ASC
    candidate_tables = await get_candidate_tables(db, request.business_id, request.party_size)

    # Query currently confirmed bookings for candidate tables at slot_start_utc
    candidate_ids = [t.get("id") or str(t.get("_id")) for t in candidate_tables]
    cursor = db["bookings"].find(
        {
            "business_id": request.business_id,
            "table_id": {"$in": candidate_ids},
            "slot_start": slot_start_utc,
            "status": BookingStatus.CONFIRMED.value,
        },
        {"table_id": 1},
    )
    occupied_records = await cursor.to_list(length=100)
    occupied_ids = {rec["table_id"] for rec in occupied_records}

    # Free candidate tables in order of preference (smallest capacity first)
    free_candidates = [
        t for t in candidate_tables if (t.get("id") or str(t.get("_id"))) not in occupied_ids
    ]

    booking_id = f"bkg_{uuid.uuid4().hex[:12]}"
    created_at = now_utc()

    # Try assigning table. If concurrent collision happens, unique index will raise
    # DuplicateKeyError. Catch it and try the next candidate table.
    assigned_table: Optional[Dict[str, Any]] = None
    tables_to_try = free_candidates if free_candidates else candidate_tables

    for table in tables_to_try:
        table_id = table.get("id") or str(table.get("_id"))
        doc = {
            "id": booking_id,
            "business_id": request.business_id,
            "table_id": table_id,
            "table_number": table["table_number"],
            "customer_name": request.customer_name.strip(),
            "customer_phone": phone,
            "party_size": request.party_size,
            "date": request.date,
            "time": request.time,
            "slot_start": slot_start_utc,
            "slot_end": slot_end_utc,
            "status": BookingStatus.CONFIRMED.value,
            "call_id": request.call_id,
            "created_at": created_at,
            "cancelled_at": None,
        }

        try:
            await db["bookings"].insert_one(doc)
            assigned_table = table
            logger.info(
                "Successfully booked Table %d for %s at %s UTC",
                table["table_number"],
                phone,
                slot_start_utc.isoformat(),
            )
            break
        except DuplicateKeyError:
            logger.warning(
                "Collision: Table %d was booked concurrently at %s. Trying next candidate table.",
                table["table_number"],
                slot_start_utc.isoformat(),
            )
            continue

    if not assigned_table:
        # All candidate tables are occupied at this slot
        avail = await check_availability(
            db, request.business_id, request.date, time_str=None, party_size=request.party_size
        )
        alternatives = find_nearest_alternative_slots(
            request.time, avail.open_slots, max_count=3
        )
        alt_msg = (
            f" Nearest available times today: {', '.join(alternatives)}."
            if alternatives
            else " No other slots are available today."
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "SLOT_UNAVAILABLE",
                "message": (
                    f"No tables are available for a party of {request.party_size} "
                    f"at {request.time} on {request.date}.{alt_msg}"
                ),
                "alternative_slots": alternatives,
            },
        )

    return BookingResponse(
        id=booking_id,
        business_id=request.business_id,
        table_id=assigned_table.get("id") or str(assigned_table.get("_id")),
        table_number=assigned_table["table_number"],
        customer_name=request.customer_name.strip(),
        customer_phone=phone,
        party_size=request.party_size,
        date=request.date,
        time=request.time,
        slot_start=slot_start_utc,
        slot_end=slot_end_utc,
        status=BookingStatus.CONFIRMED,
        call_id=request.call_id,
        created_at=created_at,
        cancelled_at=None,
    )


async def cancel_booking_by_id(
    db: AsyncIOMotorDatabase,
    booking_id: str,
) -> BookingResponse:
    """Cancel an existing booking by its ID and free the slot."""
    booking = await db["bookings"].find_one({"$or": [{"id": booking_id}, {"_id": booking_id}]})
    if not booking:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "BOOKING_NOT_FOUND",
                "message": f"Reservation '{booking_id}' not found.",
            },
        )

    if booking["status"] == BookingStatus.CANCELLED.value:
        return BookingResponse(
            id=booking["id"],
            business_id=booking["business_id"],
            table_id=booking["table_id"],
            table_number=booking["table_number"],
            customer_name=booking["customer_name"],
            customer_phone=booking["customer_phone"],
            party_size=booking["party_size"],
            date=booking["date"],
            time=booking["time"],
            slot_start=booking["slot_start"],
            slot_end=booking["slot_end"],
            status=BookingStatus.CANCELLED,
            call_id=booking.get("call_id"),
            created_at=booking["created_at"],
            cancelled_at=booking.get("cancelled_at") or now_utc(),
        )

    cancelled_at = now_utc()
    await db["bookings"].update_one(
        {"_id": booking["_id"]},
        {"$set": {"status": BookingStatus.CANCELLED.value, "cancelled_at": cancelled_at}},
    )

    logger.info("Cancelled booking %s for table %s", booking_id, booking["table_id"])

    return BookingResponse(
        id=booking["id"],
        business_id=booking["business_id"],
        table_id=booking["table_id"],
        table_number=booking["table_number"],
        customer_name=booking["customer_name"],
        customer_phone=booking["customer_phone"],
        party_size=booking["party_size"],
        date=booking["date"],
        time=booking["time"],
        slot_start=booking["slot_start"],
        slot_end=booking["slot_end"],
        status=BookingStatus.CANCELLED,
        call_id=booking.get("call_id"),
        created_at=booking["created_at"],
        cancelled_at=cancelled_at,
    )


async def cancel_booking_by_phone(
    db: AsyncIOMotorDatabase,
    request: BookingCancelByPhoneRequest,
) -> BookingResponse:
    """Cancel a booking by matching customer_phone, date, and time in business timezone."""
    phone = normalize_phone(request.customer_phone)
    business = await get_business_or_404(db, request.business_id)

    # Compute UTC slot_start for lookup (don't check future strictly so customers can cancel today's bookings)
    _, _, slot_start_utc, _ = validate_booking_datetime(
        business, request.date, request.time, check_future=False
    )

    booking = await db["bookings"].find_one(
        {
            "business_id": request.business_id,
            "customer_phone": phone,
            "slot_start": slot_start_utc,
            "status": BookingStatus.CONFIRMED.value,
        }
    )

    if not booking:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "BOOKING_NOT_FOUND",
                "message": (
                    f"No confirmed reservation found under phone {phone} for {request.date} at {request.time}."
                ),
            },
        )

    cancelled_at = now_utc()
    await db["bookings"].update_one(
        {"_id": booking["_id"]},
        {"$set": {"status": BookingStatus.CANCELLED.value, "cancelled_at": cancelled_at}},
    )

    logger.info("Cancelled booking %s by phone %s", booking["id"], phone)

    return BookingResponse(
        id=booking["id"],
        business_id=booking["business_id"],
        table_id=booking["table_id"],
        table_number=booking["table_number"],
        customer_name=booking["customer_name"],
        customer_phone=booking["customer_phone"],
        party_size=booking["party_size"],
        date=booking["date"],
        time=booking["time"],
        slot_start=booking["slot_start"],
        slot_end=booking["slot_end"],
        status=BookingStatus.CANCELLED,
        call_id=booking.get("call_id"),
        created_at=booking["created_at"],
        cancelled_at=cancelled_at,
    )
