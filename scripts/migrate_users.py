"""One-time migration: populate the unified `users` collection.

Run with: uv run python scripts/migrate_users.py

Fully idempotent — safe to re-run.

Steps:
  1. ensure_indexes     — create users collection indexes
  2. migrate_user_keys  — bootstrap user docs from user_keys
  3. backfill_tickets   — populate ticket_ids from tickets collection
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from loguru import logger
from pymongo import ASCENDING, AsyncMongoClient


MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "foundry")


async def ensure_indexes(db) -> None:  # type: ignore[no-untyped-def]
    """Create indexes on users collection."""
    await db["users"].create_index([("discord_user_id", ASCENDING)], unique=True)
    await db["users"].create_index([("rsn", ASCENDING)], sparse=True)
    await db["users"].create_index(
        [("guild_id", ASCENDING), ("discord_user_id", ASCENDING)]
    )
    logger.info("ensure_indexes: done")


async def migrate_user_keys(db) -> None:  # type: ignore[no-untyped-def]
    """Bootstrap user docs from existing user_keys collection."""
    count = 0
    async for doc in db["user_keys"].find({}):
        now = datetime.now(timezone.utc)
        await db["users"].update_one(
            {"discord_user_id": doc["discord_user_id"]},
            {
                "$setOnInsert": {
                    "discord_user_id": doc["discord_user_id"],
                    "rsn": None,
                    "clan_rank": None,
                    "ticket_ids": [],
                    "created_at": now,
                },
                "$set": {
                    "discord_username": doc.get("discord_username", ""),
                    "guild_id": doc.get("guild_id", 0),
                    "guild_name": doc.get("guild_name", ""),
                    "updated_at": now,
                },
            },
            upsert=True,
        )
        count += 1
    logger.info("migrate_user_keys: processed {} user_keys docs", count)


async def backfill_tickets(db) -> None:  # type: ignore[no-untyped-def]
    """Populate ticket_ids on existing user docs from tickets collection."""
    pipeline = [
        {"$group": {"_id": "$creator.id", "ticket_ids": {"$push": "$ticket_id"}}},
    ]
    count = 0
    async for row in await db["tickets"].aggregate(pipeline):
        discord_user_id = row["_id"]
        ticket_ids = row["ticket_ids"]
        result = await db["users"].update_one(
            {"discord_user_id": discord_user_id},
            {
                "$set": {
                    "ticket_ids": ticket_ids,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        if result.matched_count:
            count += 1
    logger.info("backfill_tickets: updated ticket_ids on {} user docs", count)


async def main() -> None:
    """Run all migration steps."""
    client = AsyncMongoClient(MONGO_URI)
    db = client[MONGO_DB]
    try:
        logger.info("Starting users migration against {}/{}", MONGO_URI, MONGO_DB)
        await ensure_indexes(db)
        await migrate_user_keys(db)
        await backfill_tickets(db)
        total = await db["users"].count_documents({})
        logger.info("Migration complete. users collection has {} documents.", total)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
