"""Pytest fixtures for backend testing with a real MongoDB test database."""

from datetime import date, datetime, timedelta, timezone
from typing import AsyncGenerator
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from backend.app.config import get_settings
from backend.app.db import ensure_indexes, get_db
from backend.app.main import app

TEST_DB_NAME = "voice_assistant_test"
TEST_BUSINESS_ID = "test_cafe_001"


def get_future_weekday_date(target_weekday: int, weeks_ahead: int = 1) -> str:
    """Return 'YYYY-MM-DD' for a target weekday (0=Mon, 1=Tue, ..., 6=Sun) in the future."""
    today = date.today()
    days_ahead = (target_weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    days_ahead += (weeks_ahead - 1) * 7
    future_date = today + timedelta(days=days_ahead)
    return future_date.strftime("%Y-%m-%d")


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """Provide a clean, indexed real MongoDB database for each test."""
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[TEST_DB_NAME]

    # Ensure clean state and indexes
    await db["businesses"].delete_many({})
    await db["tables"].delete_many({})
    await db["bookings"].delete_many({})
    await db["calls"].delete_many({})
    await db["unanswered_questions"].delete_many({})
    await ensure_indexes(db)

    # Seed demo business
    opening_hours = {
        "monday": None,  # Closed on Monday
        "tuesday": {"open": "08:00", "close": "22:00"},
        "wednesday": {"open": "08:00", "close": "22:00"},
        "thursday": {"open": "08:00", "close": "22:00"},
        "friday": {"open": "08:00", "close": "22:00"},
        "saturday": {"open": "08:00", "close": "22:00"},
        "sunday": {"open": "08:00", "close": "22:00"},
    }

    await db["businesses"].insert_one(
        {
            "id": TEST_BUSINESS_ID,
            "name": "Test Cafe",
            "phone_number": "+918012345678",
            "timezone": "Asia/Kolkata",
            "opening_hours": opening_hours,
            "faqs": [
                {"question": "Do you have wifi?", "answer": "Yes, high-speed wifi is free."},
                {"question": "Are pets allowed?", "answer": "Yes on the outdoor patio."},
            ],
            "menu_summary": "Espresso and artisan bakery.",
            "slot_minutes": 60,
            "booking_policy": "60-minute slots. Tables held for 15 minutes.",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    # Seed 8 tables: 4x 2-seaters, 3x 4-seaters, 1x 8-seater
    tables = [
        {"table_number": 1, "capacity": 2},
        {"table_number": 2, "capacity": 2},
        {"table_number": 3, "capacity": 2},
        {"table_number": 4, "capacity": 2},
        {"table_number": 5, "capacity": 4},
        {"table_number": 6, "capacity": 4},
        {"table_number": 7, "capacity": 4},
        {"table_number": 8, "capacity": 8},
    ]
    for tbl in tables:
        await db["tables"].insert_one(
            {
                "id": f"table_{TEST_BUSINESS_ID}_{tbl['table_number']}",
                "business_id": TEST_BUSINESS_ID,
                "table_number": tbl["table_number"],
                "capacity": tbl["capacity"],
                "is_active": True,
            }
        )

    yield db

    client.close()


@pytest_asyncio.fixture
async def async_client(test_db: AsyncIOMotorDatabase) -> AsyncGenerator[AsyncClient, None]:
    """Httpx AsyncClient wired with dependency override pointing to test_db."""
    def override_get_db():
        return test_db

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
