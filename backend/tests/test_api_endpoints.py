"""Comprehensive API endpoint tests using httpx AsyncClient."""

import pytest
from backend.tests.conftest import TEST_BUSINESS_ID, get_future_weekday_date


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client):
    """Verify GET /health returns 200 and ok status."""
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "voice-assistant-backend"}


@pytest.mark.asyncio
async def test_get_and_update_business(async_client):
    """Verify business retrieval with tables summary and partial update."""
    # GET business
    resp = await async_client.get(f"/businesses/{TEST_BUSINESS_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["business"]["name"] == "Test Cafe"
    assert data["tables_summary"]["total_tables"] == 8
    assert data["tables_summary"]["max_capacity"] == 8

    # PUT business update
    update_payload = {"menu_summary": "Updated coffee & pastries menu."}
    put_resp = await async_client.put(f"/businesses/{TEST_BUSINESS_ID}", json=update_payload)
    assert put_resp.status_code == 200
    assert put_resp.json()["menu_summary"] == "Updated coffee & pastries menu."


@pytest.mark.asyncio
async def test_availability_with_and_without_time(async_client):
    """Verify availability endpoint behavior when time is omitted vs specified."""
    tue_date = get_future_weekday_date(1)

    # 1. Without time: returns all open slots that day
    resp_no_time = await async_client.post(
        "/availability",
        json={"business_id": TEST_BUSINESS_ID, "date": tue_date, "party_size": 2},
    )
    assert resp_no_time.status_code == 200
    data_no_time = resp_no_time.json()
    assert "open_slots" in data_no_time
    assert len(data_no_time["open_slots"]) > 0
    assert "08:00" in data_no_time["open_slots"]
    assert "21:00" in data_no_time["open_slots"]
    # 22:00 must not be a slot start because cafe closes at 22:00 and slot duration is 60m
    assert "22:00" not in data_no_time["open_slots"]

    # 2. With specific available time
    resp_with_time = await async_client.post(
        "/availability",
        json={
            "business_id": TEST_BUSINESS_ID,
            "date": tue_date,
            "time": "12:00",
            "party_size": 4,
        },
    )
    assert resp_with_time.status_code == 200
    data_with_time = resp_with_time.json()
    assert data_with_time["is_available"] is True
    assert "available at 12:00" in data_with_time["message"]

    # 3. On closed day (Monday)
    mon_date = get_future_weekday_date(0)
    resp_closed = await async_client.post(
        "/availability",
        json={"business_id": TEST_BUSINESS_ID, "date": mon_date, "party_size": 2},
    )
    assert resp_closed.status_code == 200
    assert resp_closed.json()["is_available"] is False
    assert len(resp_closed.json()["open_slots"]) == 0


@pytest.mark.asyncio
async def test_api_booking_lifecycle_and_filters(async_client):
    """Verify booking creation, listing with filters, and cancellation via API."""
    tue_date = get_future_weekday_date(1)
    phone = "+919876543123"

    # Create booking
    create_resp = await async_client.post(
        "/bookings",
        json={
            "business_id": TEST_BUSINESS_ID,
            "customer_name": "Carol Danvers",
            "customer_phone": phone,
            "party_size": 4,
            "date": tue_date,
            "time": "15:00",
        },
    )
    assert create_resp.status_code == 201
    booking = create_resp.json()
    booking_id = booking["id"]
    assert booking["status"] == "confirmed"

    # List bookings with filters
    list_resp = await async_client.get(
        f"/bookings?business_id={TEST_BUSINESS_ID}&date={tue_date}&status=confirmed"
    )
    assert list_resp.status_code == 200
    bookings_list = list_resp.json()
    assert any(b["id"] == booking_id for b in bookings_list)

    # Cancel via PATCH /bookings/{id}/cancel
    cancel_resp = await async_client.patch(f"/bookings/{booking_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Confirm it shows as cancelled in list
    cancelled_list_resp = await async_client.get(
        f"/bookings?business_id={TEST_BUSINESS_ID}&date={tue_date}&status=cancelled"
    )
    assert any(b["id"] == booking_id for b in cancelled_list_resp.json())


@pytest.mark.asyncio
async def test_api_calls_and_unanswered_questions(async_client):
    """Verify call creation, transcript update, and unanswered question logging."""
    # 1. POST /calls
    start_resp = await async_client.post(
        "/calls", json={"business_id": TEST_BUSINESS_ID}
    )
    assert start_resp.status_code == 201
    call_id = start_resp.json()["id"]

    # 2. PATCH /calls/{id} with transcript and outcome
    update_resp = await async_client.patch(
        f"/calls/{call_id}",
        json={
            "outcome": "faq_answered",
            "transcript_item": {
                "role": "customer",
                "message": "Do you have gluten free bread?",
            },
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["outcome"] == "faq_answered"
    assert len(update_resp.json()["transcript"]) == 1

    # 3. POST /calls/{id}/unanswered
    unanswered_resp = await async_client.post(
        f"/calls/{call_id}/unanswered",
        json={"question": "Can I bring my own wedding cake?"},
    )
    assert unanswered_resp.status_code == 200
    assert unanswered_resp.json()["status"] == "logged"

    # 4. GET /unanswered
    triage_resp = await async_client.get(f"/unanswered?business_id={TEST_BUSINESS_ID}")
    assert triage_resp.status_code == 200
    questions = triage_resp.json()
    assert any("wedding cake" in q["question"] for q in questions)
