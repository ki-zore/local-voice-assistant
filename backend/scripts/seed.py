"""Idempotent seed script to initialize demo cafe data in MongoDB."""

import asyncio
from datetime import datetime, timezone
import os
import sys

# Ensure repository root is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from backend.app.config import get_settings
from backend.app.db import close_db_connection, ensure_indexes, get_db

DEMO_BUSINESS_ID = "cafe_demo_001"

DEMO_FAQS = [
    {
        "question": "What are your opening hours?",
        "answer": (
            "We are open Tuesday through Sunday from 8:00 AM to 10:00 PM. "
            "We are closed every Monday for kitchen maintenance."
        ),
    },
    {
        "question": "Where is the cafe located?",
        "answer": "We are located at 124 Heritage Boulevard, Indiranagar, Bengaluru, near Metro Pillar 42.",
    },
    {
        "question": "Is parking available at the cafe?",
        "answer": "Yes, complimentary valet parking is available for all guests right in front of the cafe entrance.",
    },
    {
        "question": "Do you provide complimentary Wi-Fi?",
        "answer": "Yes, high-speed complimentary Wi-Fi is available. The network password is displayed on every table.",
    },
    {
        "question": "Do you offer vegan, dairy-free, or gluten-free options?",
        "answer": (
            "Yes, we have oat and almond milk for coffee, a dedicated vegan brunch section, "
            "and several gluten-free salads and pastries."
        ),
    },
    {
        "question": "Are pets allowed in the cafe?",
        "answer": "Yes, our covered outdoor patio seating is completely pet-friendly, and we provide water bowls for dogs.",
    },
    {
        "question": "What is your table reservation policy?",
        "answer": (
            "Reservations can be booked in 1-hour slots up to 14 days in advance. "
            "We hold reserved tables for up to 15 minutes past the scheduled booking time."
        ),
    },
    {
        "question": "What payment methods do you accept?",
        "answer": "We accept all major credit and debit cards, UPI, Google Pay, Apple Pay, and cash.",
    },
    {
        "question": "Is the cafe kid-friendly?",
        "answer": "Yes, we are family-friendly with comfortable high chairs and a dedicated kids' snack and hot chocolate menu.",
    },
    {
        "question": "Can I order takeaway or takeout in advance?",
        "answer": "Yes, our entire coffee, bakery, and food menu is available for takeaway counter pickup.",
    },
]

DEMO_TABLES = [
    # 4x two-seaters
    {"table_number": 1, "capacity": 2},
    {"table_number": 2, "capacity": 2},
    {"table_number": 3, "capacity": 2},
    {"table_number": 4, "capacity": 2},
    # 3x four-seaters
    {"table_number": 5, "capacity": 4},
    {"table_number": 6, "capacity": 4},
    {"table_number": 7, "capacity": 4},
    # 1x eight-seater
    {"table_number": 8, "capacity": 8},
]


async def seed_demo_data(target_db_name: str | None = None) -> str:
    """Seed the demo business and tables idempotently."""
    settings = get_settings()
    db = get_db(target_db_name or settings.mongodb_db_name)

    print(f"Connecting to MongoDB database: {db.name}")
    await ensure_indexes(db)

    # 1. Upsert Demo Cafe business document
    opening_hours = {
        "monday": None,  # Closed on Mondays
        "tuesday": {"open": "08:00", "close": "22:00"},
        "wednesday": {"open": "08:00", "close": "22:00"},
        "thursday": {"open": "08:00", "close": "22:00"},
        "friday": {"open": "08:00", "close": "22:00"},
        "saturday": {"open": "08:00", "close": "22:00"},
        "sunday": {"open": "08:00", "close": "22:00"},
    }

    business_doc = {
        "id": DEMO_BUSINESS_ID,
        "name": "Demo Cafe",
        "phone_number": "+918023456789",
        "timezone": "Asia/Kolkata",
        "opening_hours": opening_hours,
        "faqs": DEMO_FAQS,
        "menu_summary": (
            "Artisan espresso, manual pour-overs, sourdough tartines, all-day brunch, "
            "wood-fired sourdough flatbreads, organic acai bowls, and fresh French pastries."
        ),
        "slot_minutes": 60,
        "booking_policy": (
            "Reservations are in 60-minute slots. Tables are held for 15 minutes past booking time. "
            "Cancellations are free. Groups over 8 guests should call the cafe directly."
        ),
        "updated_at": datetime.now(timezone.utc),
    }

    await db["businesses"].update_one(
        {"$or": [{"id": DEMO_BUSINESS_ID}, {"_id": DEMO_BUSINESS_ID}]},
        {
            "$set": business_doc,
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )
    print(f"Upserted business: '{business_doc['name']}' (ID: {DEMO_BUSINESS_ID})")

    # 2. Upsert Tables
    for tbl in DEMO_TABLES:
        table_id = f"table_{DEMO_BUSINESS_ID}_{tbl['table_number']}"
        await db["tables"].update_one(
            {"business_id": DEMO_BUSINESS_ID, "table_number": tbl["table_number"]},
            {
                "$set": {
                    "id": table_id,
                    "business_id": DEMO_BUSINESS_ID,
                    "table_number": tbl["table_number"],
                    "capacity": tbl["capacity"],
                    "is_active": True,
                }
            },
            upsert=True,
        )
    print(f"Upserted {len(DEMO_TABLES)} tables (4x 2-seaters, 3x 4-seaters, 1x 8-seater)")

    print(f"\nSeed completed successfully!")
    print(f"BUSINESS_ID: {DEMO_BUSINESS_ID}")
    return DEMO_BUSINESS_ID


async def main() -> None:
    try:
        await seed_demo_data()
    finally:
        close_db_connection()


if __name__ == "__main__":
    asyncio.run(main())
