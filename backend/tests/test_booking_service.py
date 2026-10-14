"""Test suite for core booking service and business logic."""

from datetime import datetime, timezone
import pytest
from fastapi import HTTPException

from backend.app.models.booking import (
    BookingCancelByPhoneRequest,
    BookingCreateRequest,
    BookingStatus,
)
from backend.app.services.booking_service import (
    cancel_booking_by_id,
    cancel_booking_by_phone,
    create_booking,
    get_candidate_tables,
    normalize_phone,
    validate_booking_datetime,
)
from backend.tests.conftest import TEST_BUSINESS_ID, get_future_weekday_date


@pytest.mark.asyncio
async def test_successful_booking(test_db):
    """Verify that a valid booking is successfully created and stored."""
    tue_date = get_future_weekday_date(1)  # Tuesday
    req = BookingCreateRequest(
        business_id=TEST_BUSINESS_ID,
        customer_name="Alice Johnson",
        customer_phone="+919876543210",
        party_size=2,
        date=tue_date,
        time="18:00",
    )

    response = await create_booking(test_db, req)
    assert response.status == BookingStatus.CONFIRMED
    assert response.customer_name == "Alice Johnson"
    assert response.customer_phone == "+919876543210"
    assert response.party_size == 2
    assert response.date == tue_date
    assert response.time == "18:00"
    assert response.table_number in [1, 2, 3, 4]  # Capacity 2 table

    # Verify document in MongoDB
    saved = await test_db["bookings"].find_one({"id": response.id})
    assert saved is not None
    assert saved["status"] == "confirmed"


@pytest.mark.asyncio
async def test_smallest_fitting_table_assignment(test_db):
    """Verify tables are assigned by smallest fitting capacity first."""
    tue_date = get_future_weekday_date(1)

    # Party size 2 should get a 2-seater (table 1-4)
    res_2 = await create_booking(
        test_db,
        BookingCreateRequest(
            business_id=TEST_BUSINESS_ID,
            customer_name="Guest Two",
            customer_phone="9876543211",
            party_size=2,
            date=tue_date,
            time="14:00",
        ),
    )
    table_doc_2 = await test_db["tables"].find_one({"id": res_2.table_id})
    assert table_doc_2["capacity"] == 2

    # Party size 3 should get a 4-seater (table 5-7), NOT the 8-seater
    res_3 = await create_booking(
        test_db,
        BookingCreateRequest(
            business_id=TEST_BUSINESS_ID,
            customer_name="Guest Three",
            customer_phone="9876543212",
            party_size=3,
            date=tue_date,
            time="14:00",
        ),
    )
    table_doc_3 = await test_db["tables"].find_one({"id": res_3.table_id})
    assert table_doc_3["capacity"] == 4

    # Party size 7 should get the 8-seater (table 8)
    res_7 = await create_booking(
        test_db,
        BookingCreateRequest(
            business_id=TEST_BUSINESS_ID,
            customer_name="Guest Seven",
            customer_phone="9876543213",
            party_size=7,
            date=tue_date,
            time="14:00",
        ),
    )
    table_doc_7 = await test_db["tables"].find_one({"id": res_7.table_id})
    assert table_doc_7["capacity"] == 8


@pytest.mark.asyncio
async def test_party_size_larger_than_any_table(test_db):
    """Verify that a party exceeding maximum single-table capacity is rejected with clear error."""
    tue_date = get_future_weekday_date(1)
    req = BookingCreateRequest(
        business_id=TEST_BUSINESS_ID,
        customer_name="Huge Group",
        customer_phone="9876543210",
        party_size=9,  # Max table is 8
        date=tue_date,
        time="15:00",
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_booking(test_db, req)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "PARTY_TOO_LARGE"
    assert "exceeds our maximum single-table capacity of 8" in exc_info.value.detail["message"]


@pytest.mark.asyncio
async def test_timezone_correctness(test_db):
    """Verify that local 19:00 IST is stored as 13:30 UTC in MongoDB."""
    tue_date = get_future_weekday_date(1)
    req = BookingCreateRequest(
        business_id=TEST_BUSINESS_ID,
        customer_name="Timezone Tester",
        customer_phone="9876543210",
        party_size=2,
        date=tue_date,
        time="19:00",
    )

    res = await create_booking(test_db, req)
    saved = await test_db["bookings"].find_one({"id": res.id})

    # Asia/Kolkata is UTC+5:30.
    # 19:00 IST - 5:30 = 13:30 UTC.
    slot_utc = saved["slot_start"]
    # MongoDB returns naive datetime in UTC
    assert slot_utc.hour == 13
    assert slot_utc.minute == 30


@pytest.mark.asyncio
async def test_cancelled_booking_frees_slot_for_rebooking(test_db):
    """Verify that cancelling a booking removes conflict via partial index, allowing rebooking."""
    tue_date = get_future_weekday_date(1)

    # Book all 4 two-seater tables for 16:00
    b1 = await create_booking(
        test_db,
        BookingCreateRequest(
            business_id=TEST_BUSINESS_ID,
            customer_name="P1",
            customer_phone="9876540001",
            party_size=2,
            date=tue_date,
            time="16:00",
        ),
    )
    b2 = await create_booking(
        test_db,
        BookingCreateRequest(
            business_id=TEST_BUSINESS_ID,
            customer_name="P2",
            customer_phone="9876540002",
            party_size=2,
            date=tue_date,
            time="16:00",
        ),
    )
    b3 = await create_booking(
        test_db,
        BookingCreateRequest(
            business_id=TEST_BUSINESS_ID,
            customer_name="P3",
            customer_phone="9876540003",
            party_size=2,
            date=tue_date,
            time="16:00",
        ),
    )
    b4 = await create_booking(
        test_db,
        BookingCreateRequest(
            business_id=TEST_BUSINESS_ID,
            customer_name="P4",
            customer_phone="9876540004",
            party_size=2,
            date=tue_date,
            time="16:00",
        ),
    )

    # Cancel b1
    cancelled = await cancel_booking_by_id(test_db, b1.id)
    assert cancelled.status == BookingStatus.CANCELLED

    # Now a new booking for party of 2 at 16:00 should succeed on the freed table!
    rebooked = await create_booking(
        test_db,
        BookingCreateRequest(
            business_id=TEST_BUSINESS_ID,
            customer_name="New Guest",
            customer_phone="9876540005",
            party_size=2,
            date=tue_date,
            time="16:00",
        ),
    )
    assert rebooked.status == BookingStatus.CONFIRMED
    assert rebooked.table_id == b1.table_id


@pytest.mark.asyncio
async def test_booking_slot_conflict_returns_alternatives(test_db):
    """Verify that when all suitable tables are booked, conflict 409 is raised with alternative slots."""
    tue_date = get_future_weekday_date(1)

    # Table 8 is the only 8-seater
    await create_booking(
        test_db,
        BookingCreateRequest(
            business_id=TEST_BUSINESS_ID,
            customer_name="Group One",
            customer_phone="9876541111",
            party_size=8,
            date=tue_date,
            time="17:00",
        ),
    )

    # Attempting to book the 8-seater at the same time must trigger 409 with alternatives
    with pytest.raises(HTTPException) as exc_info:
        await create_booking(
            test_db,
            BookingCreateRequest(
                business_id=TEST_BUSINESS_ID,
                customer_name="Group Two",
                customer_phone="9876542222",
                party_size=8,
                date=tue_date,
                time="17:00",
            ),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "SLOT_UNAVAILABLE"
    assert "No tables are available" in exc_info.value.detail["message"]
    # Alternative slots must be provided
    assert len(exc_info.value.detail["alternative_slots"]) > 0
    assert "17:00" not in exc_info.value.detail["alternative_slots"]


@pytest.mark.asyncio
async def test_validation_rules(test_db):
    """Verify rejection of past dates, closed days, out-of-hours, and slots crossing closing time."""
    business = await test_db["businesses"].find_one({"id": TEST_BUSINESS_ID})

    # 1. Past date
    with pytest.raises(HTTPException) as exc_past:
        validate_booking_datetime(business, "2020-01-01", "10:00", check_future=True)
    assert exc_past.value.detail["error"] == "PAST_TIME"

    # 2. Closed day (Monday)
    mon_date = get_future_weekday_date(0)  # Monday
    with pytest.raises(HTTPException) as exc_closed:
        validate_booking_datetime(business, mon_date, "10:00", check_future=True)
    assert exc_closed.value.detail["error"] == "CLOSED_DAY"
    assert "closed on Mondays" in exc_closed.value.detail["message"]

    # 3. Before opening hours (e.g. 07:00 when opens at 08:00)
    tue_date = get_future_weekday_date(1)
    with pytest.raises(HTTPException) as exc_early:
        validate_booking_datetime(business, tue_date, "07:00", check_future=True)
    assert exc_early.value.detail["error"] == "OUTSIDE_HOURS"

    # 4. At closing time (22:00 starting slot would end at 23:00, outside hours)
    with pytest.raises(HTTPException) as exc_late:
        validate_booking_datetime(business, tue_date, "22:00", check_future=True)
    assert exc_late.value.detail["error"] in ["OUTSIDE_HOURS", "SLOT_EXCEEDS_CLOSING"]

    # 5. Unaligned slot (e.g. 18:15 when slot_minutes=60)
    with pytest.raises(HTTPException) as exc_align:
        validate_booking_datetime(business, tue_date, "18:15", check_future=True)
    assert exc_align.value.detail["error"] == "SLOT_NOT_ALIGNED"


@pytest.mark.asyncio
async def test_cancel_by_phone(test_db):
    """Verify cancel-by-phone happy path and not-found handling."""
    tue_date = get_future_weekday_date(1)
    phone = "+919876543999"

    # Create a booking
    res = await create_booking(
        test_db,
        BookingCreateRequest(
            business_id=TEST_BUSINESS_ID,
            customer_name="Bob Cancel",
            customer_phone=phone,
            party_size=2,
            date=tue_date,
            time="11:00",
        ),
    )

    # Cancel via phone match
    cancel_req = BookingCancelByPhoneRequest(
        business_id=TEST_BUSINESS_ID,
        customer_phone="9876543999",  # Without plus, checks normalization
        date=tue_date,
        time="11:00",
    )
    cancelled = await cancel_booking_by_phone(test_db, cancel_req)
    assert cancelled.status == BookingStatus.CANCELLED
    assert cancelled.id == res.id

    # Second cancellation attempt should return 404 (already cancelled/no active booking)
    with pytest.raises(HTTPException) as exc_info:
        await cancel_booking_by_phone(test_db, cancel_req)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "BOOKING_NOT_FOUND"
