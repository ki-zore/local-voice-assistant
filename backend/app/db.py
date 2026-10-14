"""Database connection management and MongoDB index creation using Motor."""

import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import pymongo

from backend.app.config import get_settings

logger = logging.getLogger("voice_assistant.db")

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


def get_client() -> AsyncIOMotorClient:
    """Return the global AsyncIOMotorClient instance."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client


def get_db(db_name: Optional[str] = None) -> AsyncIOMotorDatabase:
    """Return the AsyncIOMotorDatabase instance."""
    global _db
    client = get_client()
    if db_name:
        return client[db_name]
    if _db is None:
        settings = get_settings()
        _db = client[settings.mongodb_db_name]
    return _db


def close_db_connection() -> None:
    """Close the database client connection."""
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed.")


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create all required indexes, especially the unique compound booking index."""
    logger.info("Ensuring database indexes on database '%s'...", db.name)

    # 1. Bookings indexes
    # CRITICAL: Unique compound index on (business_id, table_id, slot_start)
    # with partialFilterExpression { status: "confirmed" }
    # This prevents double booking while letting cancelled bookings free the slot.
    await db["bookings"].create_index(
        [
            ("business_id", pymongo.ASCENDING),
            ("table_id", pymongo.ASCENDING),
            ("slot_start", pymongo.ASCENDING),
        ],
        unique=True,
        name="uniq_confirmed_business_table_slot",
        partialFilterExpression={"status": "confirmed"},
    )

    await db["bookings"].create_index(
        [
            ("business_id", pymongo.ASCENDING),
            ("slot_start", pymongo.ASCENDING),
        ],
        name="idx_bookings_business_slot_start",
    )

    await db["bookings"].create_index(
        [
            ("business_id", pymongo.ASCENDING),
            ("customer_phone", pymongo.ASCENDING),
        ],
        name="idx_bookings_business_phone",
    )

    # 2. Tables indexes
    await db["tables"].create_index(
        [
            ("business_id", pymongo.ASCENDING),
            ("table_number", pymongo.ASCENDING),
        ],
        unique=True,
        name="uniq_business_table_number",
    )

    await db["tables"].create_index(
        [
            ("business_id", pymongo.ASCENDING),
            ("capacity", pymongo.ASCENDING),
        ],
        name="idx_tables_business_capacity",
    )

    # 3. Businesses index
    await db["businesses"].create_index(
        [("id", pymongo.ASCENDING)],
        unique=True,
        name="uniq_business_id",
    )

    # 4. Calls indexes
    await db["calls"].create_index(
        [
            ("business_id", pymongo.ASCENDING),
            ("started_at", pymongo.DESCENDING),
        ],
        name="idx_calls_business_started_at",
    )

    # 5. Unanswered questions triage index
    await db["unanswered_questions"].create_index(
        [
            ("business_id", pymongo.ASCENDING),
            ("created_at", pymongo.DESCENDING),
        ],
        name="idx_unanswered_business_created_at",
    )

    logger.info("All MongoDB indexes successfully ensured.")
