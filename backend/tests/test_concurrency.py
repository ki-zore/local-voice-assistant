"""Concurrency tests verifying double-booking prevention under race conditions."""

import asyncio
import pytest
from fastapi import HTTPException

from backend.app.models.booking import BookingCreateRequest, BookingStatus
from backend.app.services.booking_service import create_booking
from backend.tests.conftest import TEST_BUSINESS_ID, get_future_weekday_date


@pytest.mark.asyncio
async def test_two_concurrent_bookings_for_last_remaining_table(test_db):
    """Verify that under concurrent requests for the only available table, exactly one succeeds."""
    tue_date = get_future_weekday_date(1)

    # Party size 8 can only be seated at Table 8 (the single 8-seater)
    req1 = BookingCreateRequest(
        business_id=TEST_BUSINESS_ID,
        customer_name="Concurrent Caller A",
        customer_phone="+919876500001",
        party_size=8,
        date=tue_date,
        time="20:00",
    )
    req2 = BookingCreateRequest(
        business_id=TEST_BUSINESS_ID,
        customer_name="Concurrent Caller B",
        customer_phone="+919876500002",
        party_size=8,
        date=tue_date,
        time="20:00",
    )

    # Launch both booking attempts concurrently
    results = await asyncio.gather(
        create_booking(test_db, req1),
        create_booking(test_db, req2),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    # Exactly one must succeed and one must fail
    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(failures) == 1, f"Expected 1 failure, got {len(failures)}"

    # Check successful booking
    successful_res = successes[0]
    assert successful_res.status == BookingStatus.CONFIRMED
    assert successful_res.table_number == 8

    # Check rejected booking
    failed_exc = failures[0]
    assert isinstance(failed_exc, HTTPException)
    assert failed_exc.status_code == 409
    assert failed_exc.detail["error"] == "SLOT_UNAVAILABLE"
    assert "alternative_slots" in failed_exc.detail

    # Verify database has exactly 1 confirmed record for this slot
    total_confirmed = await test_db["bookings"].count_documents(
        {
            "business_id": TEST_BUSINESS_ID,
            "date": tue_date,
            "time": "20:00",
            "status": "confirmed",
        }
    )
    assert total_confirmed == 1
