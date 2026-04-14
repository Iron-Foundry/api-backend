"""One-time migration: MongoDB → PostgreSQL.

Run with: docker compose exec api-backend uv run python scripts/migrate_mongo_to_postgres.py

Idempotent for tables with natural unique keys (users, tickets, survey_templates,
role_panels, leaderboards, metrics, config) — ON CONFLICT DO NOTHING.

Event tables (events, coffer_events, membership_events) use BIGSERIAL with no
natural dedup key — re-running will insert duplicates in those tables.

Apply alembic 0002 before running:
    docker compose exec api-backend uv run alembic upgrade head
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from datetime import datetime, timezone
from typing import Any

import asyncpg
from loguru import logger
from pymongo import AsyncMongoClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "foundry")
DATABASE_URL = os.getenv("DATABASE_URL", "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pg_dsn(url: str) -> str:
    """Strip SQLAlchemy driver prefix so asyncpg can parse the DSN."""
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgres+asyncpg://", "postgresql://")
    )


def _to_dt(val: Any) -> datetime | None:
    """Coerce a MongoDB datetime (or None) to a UTC-aware datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    return None


def _json_serial(obj: Any) -> Any:
    """Fallback JSON serialiser for non-standard types inside JSONB values."""
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.isoformat()
    # ObjectId, Decimal128, etc. — stringify
    return str(obj)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, default=_json_serial)


def _sanitise_doc(val: Any) -> Any:
    """Recursively base64-encode bytes; leave everything else untouched."""
    if isinstance(val, bytes):
        return base64.b64encode(val).decode()
    if isinstance(val, dict):
        return {k: _sanitise_doc(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_sanitise_doc(v) for v in val]
    return val


def _sanitise_config_value(doc: dict[str, Any]) -> dict[str, Any]:
    """Strip _id / guild_id; base64-encode any bytes fields (ticket images)."""
    return {k: _sanitise_doc(v) for k, v in doc.items() if k not in ("_id", "guild_id")}


# ---------------------------------------------------------------------------
# 1. survey_templates (no FK deps)
# ---------------------------------------------------------------------------


async def migrate_survey_templates(db: Any, pg: asyncpg.Connection) -> int:
    migrated = skipped = 0
    async for doc in db["survey_templates"].find({}):
        template_id = doc.get("template_id") or str(doc["_id"])
        raw_fields = doc.get("fields") or doc.get("questions") or []
        questions = [
            {
                "id": f.get("id"),
                "text": f.get("label") or f.get("text") or "",
                "type": f.get("type", "text"),
                "required": f.get("required", False),
                "options": f.get("options") or [],
            }
            for f in raw_fields
        ]
        try:
            await pg.execute(
                """
                INSERT INTO survey_templates (template_id, title, questions, created_at)
                VALUES ($1, $2, $3::jsonb, $4)
                ON CONFLICT DO NOTHING
                """,
                template_id,
                doc.get("title") or "",
                _dumps(questions),
                _to_dt(doc.get("created_at")),
            )
            migrated += 1
        except Exception as exc:
            logger.warning("survey_templates skip {}: {}", template_id, exc)
            skipped += 1
    logger.info("survey_templates: migrated={} skipped={}", migrated, skipped)
    return migrated


# ---------------------------------------------------------------------------
# 2. users (no FK deps — joins user_keys + temp_vc_users)
# ---------------------------------------------------------------------------


async def migrate_users(db: Any, pg: asyncpg.Connection) -> int:
    # Build lookup maps from related collections
    key_map: dict[int, dict[str, Any]] = {}
    async for doc in db["user_keys"].find({}):
        uid = doc.get("discord_user_id")
        if uid is not None:
            key_map[int(uid)] = doc

    vc_map: dict[int, dict[str, Any]] = {}
    async for doc in db["temp_vc_users"].find({}):
        uid = doc.get("user_id") or doc.get("discord_user_id")
        if uid is not None:
            vc_map[int(uid)] = doc

    migrated = skipped = 0
    async for doc in db["users"].find({}):
        uid = doc.get("discord_user_id")
        if uid is None:
            skipped += 1
            continue
        uid = int(uid)
        key_doc = key_map.get(uid, {})
        vc_doc = vc_map.get(uid, {})

        vc_private = vc_doc.get("private")
        if vc_private is True:
            lock_status: str | None = "locked"
        elif vc_private is False:
            lock_status = "unlocked"
        else:
            lock_status = None

        try:
            await pg.execute(
                """
                INSERT INTO users (
                    discord_user_id, discord_username, guild_id,
                    rsn, clan_rank, discord_roles,
                    ticket_ids, total_loot_value, clan_donated,
                    collection_log_slots, collection_log_slots_max,
                    stats_opt_out,
                    api_key, key_is_active, key_created_at, key_expires_at,
                    temp_vc_lock_status, temp_vc_member_limit, temp_vc_bitrate,
                    created_at, updated_at
                ) VALUES (
                    $1,  $2,  $3,
                    $4,  $5,  $6,
                    $7,  $8,  $9,
                    $10, $11,
                    $12,
                    $13, $14, $15, $16,
                    $17, $18, $19,
                    $20, $21
                )
                ON CONFLICT DO NOTHING
                """,
                uid,
                doc.get("discord_username") or "",
                int(doc.get("guild_id") or 0),
                doc.get("rsn"),
                doc.get("clan_rank"),
                doc.get("discord_roles") or [],
                [int(x) for x in (doc.get("ticket_ids") or [])],
                int(doc.get("total_loot_value") or 0),
                0,  # clan_donated — recomputable from coffer_events
                int(doc.get("collection_log_slots") or 0),
                0,  # collection_log_slots_max — no MongoDB equivalent
                bool(doc.get("stats_opt_out") or False),
                key_doc.get("key"),
                bool(key_doc.get("is_active") or False),
                _to_dt(key_doc.get("created_at")),
                None,  # key_expires_at — no MongoDB equivalent
                lock_status,
                None,  # temp_vc_member_limit — no MongoDB equivalent
                None,  # temp_vc_bitrate — no MongoDB equivalent
                _to_dt(doc.get("created_at")) or datetime.now(timezone.utc),
                _to_dt(doc.get("updated_at")) or datetime.now(timezone.utc),
            )
            migrated += 1
        except Exception as exc:
            logger.warning("users skip {}: {}", uid, exc)
            skipped += 1
    logger.info("users: migrated={} skipped={}", migrated, skipped)
    return migrated


# ---------------------------------------------------------------------------
# 3. events (no FK deps — 12 collections → unified table)
# ---------------------------------------------------------------------------

EVENT_COLLECTIONS: list[tuple[str, str]] = [
    ("loot_events", "loot"),
    ("level_events", "level"),
    ("xp_events", "xp"),
    ("achievement_events", "achievement"),
    ("pet_events", "pet"),
    ("collection_log_events", "collection_log"),
    ("loot_key_events", "loot_key"),
    ("clue_events", "clue"),
    ("pk_events", "pk"),
    ("personal_best_events", "personal_best"),
    ("hcim_death_events", "hcim_death"),
    ("unknown_broadcasts", "unknown"),
]


def _build_event_data(event_type: str, doc: dict[str, Any]) -> dict[str, Any]:
    if event_type == "loot":
        return {
            "item_name": doc.get("item_name"),
            "coin_value": doc.get("coin_value"),
            "source": doc.get("source"),
        }
    if event_type == "level":
        return {"skill": doc.get("skill"), "new_level": doc.get("new_level")}
    if event_type == "xp":
        return {"skill": doc.get("skill"), "xp": doc.get("xp")}
    if event_type == "achievement":
        return {
            "achievement_type": doc.get("achievement_type"),
            # MongoDB stores as achievement_name; PG schema uses name
            "name": doc.get("achievement_name") or doc.get("name"),
        }
    if event_type == "collection_log":
        return {"item_name": doc.get("item_name")}
    if event_type == "loot_key":
        return {"coin_value": doc.get("coin_value")}
    if event_type == "clue":
        return {"item_name": doc.get("item_name"), "coin_value": doc.get("coin_value")}
    if event_type == "pk":
        return {
            "winner": doc.get("winner"),
            "loser": doc.get("loser"),
            "gp_exchanged": doc.get("gp_exchanged"),
        }
    if event_type == "personal_best":
        duration_ms = int(doc.get("duration_ms") or 0)
        return {
            "activity": doc.get("activity"),
            "time_seconds": duration_ms // 1000,
            "variant": doc.get("variant") or "",
        }
    # pet, hcim_death, unknown — empty data
    return {}


async def migrate_events(
    db: Any, pg: asyncpg.Connection, rsn_map: dict[str, int]
) -> int:
    """rsn_map: LOWER(rsn) → discord_user_id, built from already-migrated users."""
    migrated = skipped = 0
    for collection, event_type in EVENT_COLLECTIONS:
        coll_count = 0
        async for doc in db[collection].find({}):
            player_name: str | None = doc.get("player_name")
            discord_user_id = (
                rsn_map.get(player_name.lower()) if player_name else None
            )
            data = _build_event_data(event_type, doc)
            try:
                await pg.execute(
                    """
                    INSERT INTO events (
                        type, timestamp, player_name, sender,
                        is_league_world, raw_message, data, discord_user_id
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
                    """,
                    event_type,
                    _to_dt(doc.get("timestamp")) or datetime.now(timezone.utc),
                    player_name,
                    doc.get("sender"),
                    bool(doc.get("is_league_world") or False),
                    doc.get("raw_message"),
                    _dumps(data),
                    discord_user_id,
                )
                coll_count += 1
                migrated += 1
            except Exception as exc:
                logger.warning("events/{} skip: {}", collection, exc)
                skipped += 1
        logger.info("events/{}: inserted={}", collection, coll_count)
    logger.info("events total: migrated={} skipped={}", migrated, skipped)
    return migrated


# ---------------------------------------------------------------------------
# 4. coffer_events (no FK deps)
# ---------------------------------------------------------------------------


async def migrate_coffer_events(db: Any, pg: asyncpg.Connection) -> int:
    migrated = skipped = 0
    async for doc in db["coffer_events"].find({}):
        event_type = doc.get("event_type", "")
        is_donation = event_type == "deposit"
        try:
            await pg.execute(
                """
                INSERT INTO coffer_events (
                    timestamp, player_name, sender,
                    is_league_world, raw_message, amount, is_donation
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                _to_dt(doc.get("timestamp")) or datetime.now(timezone.utc),
                doc.get("player_name") or "",
                doc.get("sender"),
                bool(doc.get("is_league_world") or False),
                doc.get("raw_message"),
                int(doc.get("amount") or 0),
                is_donation,
            )
            migrated += 1
        except Exception as exc:
            logger.warning("coffer_events skip: {}", exc)
            skipped += 1
    logger.info("coffer_events: migrated={} skipped={}", migrated, skipped)
    return migrated


# ---------------------------------------------------------------------------
# 5. membership_events (no FK deps)
# Source: MongoDB `member_events` (join/leave/expelled).
# Skip MongoDB `membership_events` (paid membership — no PG table).
# ---------------------------------------------------------------------------


async def migrate_membership_events(db: Any, pg: asyncpg.Connection) -> int:
    migrated = skipped = 0
    async for doc in db["member_events"].find({}):
        event_type = doc.get("event_type", "")
        metadata = doc.get("metadata") or {}
        expelled_by: str | None = (
            metadata.get("expelled_by") if event_type == "expelled" else None
        )
        try:
            await pg.execute(
                """
                INSERT INTO membership_events (
                    timestamp, player_name, sender,
                    is_league_world, raw_message, expelled_by
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                _to_dt(doc.get("timestamp")) or datetime.now(timezone.utc),
                doc.get("player_name") or "",
                doc.get("sender"),
                bool(doc.get("is_league_world") or False),
                doc.get("raw_message"),
                expelled_by,
            )
            migrated += 1
        except Exception as exc:
            logger.warning("membership_events skip: {}", exc)
            skipped += 1
    logger.info("membership_events: migrated={} skipped={}", migrated, skipped)
    return migrated


# ---------------------------------------------------------------------------
# 6. leaderboards (no FK deps)
# Source: MongoDB `personal_bests`
# ---------------------------------------------------------------------------


async def migrate_leaderboards(db: Any, pg: asyncpg.Connection) -> int:
    migrated = skipped = 0
    async for doc in db["personal_bests"].find({}):
        player_name = doc.get("player_name") or ""
        activity = doc.get("activity") or ""
        variant = doc.get("variant") or ""
        duration_ms = int(doc.get("duration_ms") or 0)
        time_seconds = duration_ms // 1000
        try:
            await pg.execute(
                """
                INSERT INTO leaderboards (player_name, activity, variant, time_seconds)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (player_name, activity, variant)
                DO UPDATE SET time_seconds = LEAST(leaderboards.time_seconds, EXCLUDED.time_seconds)
                """,
                player_name,
                activity,
                variant,
                time_seconds,
            )
            migrated += 1
        except Exception as exc:
            logger.warning("leaderboards skip: {}", exc)
            skipped += 1
    logger.info("leaderboards: migrated={} skipped={}", migrated, skipped)
    return migrated


# ---------------------------------------------------------------------------
# 7. metrics (no FK deps)
# Source: MongoDB `fun_metrics`
# ---------------------------------------------------------------------------


async def migrate_metrics(db: Any, pg: asyncpg.Connection) -> int:
    migrated = skipped = 0
    async for doc in db["fun_metrics"].find({}):
        metric_id = str(doc["_id"])
        count = doc.get("count")
        achieved_at = _to_dt(doc.get("achieved_at"))
        try:
            await pg.execute(
                """
                INSERT INTO metrics (id, count, total_value, achieved_at, last_updated)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT DO NOTHING
                """,
                metric_id,
                count,
                None,       # total_value — no MongoDB equivalent
                achieved_at,
                achieved_at,  # last_updated = achieved_at
            )
            migrated += 1
        except Exception as exc:
            logger.warning("metrics skip {}: {}", metric_id, exc)
            skipped += 1
    logger.info("metrics: migrated={} skipped={}", migrated, skipped)
    return migrated


# ---------------------------------------------------------------------------
# 8. config (no FK deps — 7 MongoDB collections → (guild_id, key) rows)
# ---------------------------------------------------------------------------

CONFIG_COLLECTIONS: list[tuple[str, str]] = [
    ("panel_config", "panel"),
    ("ticket_config", "ticket"),
    ("action_log_config", "action_log"),
    ("broadcast_config", "broadcast"),
    ("join_roles", "join_roles"),
    ("chat_events_config", "chat_events"),
    ("temp_vc", "temp_vc"),
]


async def migrate_config(db: Any, pg: asyncpg.Connection) -> int:
    migrated = skipped = 0
    for collection, key in CONFIG_COLLECTIONS:
        async for doc in db[collection].find({}):
            guild_id = doc.get("guild_id")
            if guild_id is None:
                skipped += 1
                continue
            value = _sanitise_config_value(doc)
            try:
                await pg.execute(
                    """
                    INSERT INTO config (guild_id, key, value)
                    VALUES ($1, $2, $3::jsonb)
                    ON CONFLICT DO NOTHING
                    """,
                    int(guild_id),
                    key,
                    _dumps(value),
                )
                migrated += 1
            except Exception as exc:
                logger.warning(
                    "config/{} skip guild {}: {}", collection, guild_id, exc
                )
                skipped += 1
    logger.info("config: migrated={} skipped={}", migrated, skipped)
    return migrated


# ---------------------------------------------------------------------------
# 9. tickets (logically after users)
# ---------------------------------------------------------------------------


async def migrate_tickets(db: Any, pg: asyncpg.Connection) -> int:
    migrated = skipped = 0
    async for doc in db["tickets"].find({}):
        ticket_id = doc.get("ticket_id")
        if ticket_id is None:
            skipped += 1
            continue
        ticket_id = int(ticket_id)

        creator = doc.get("creator") or {}
        status_raw = doc.get("status")
        # MongoDB stores TicketStatus as the enum value string
        if hasattr(status_raw, "value"):
            status = status_raw.value
        elif isinstance(status_raw, str):
            status = status_raw
        else:
            status = "open"

        reopen_history = doc.get("reopen_history") or []
        metadata = doc.get("metadata") or {}
        assigned_staff = [int(x) for x in (doc.get("assigned_staff") or [])]
        participants = [int(x) for x in (doc.get("participants") or [])]

        try:
            await pg.execute(
                """
                INSERT INTO tickets (
                    ticket_id, guild_id, ticket_type, status,
                    created_at, closed_at, last_message_at,
                    channel_id, creator_id, creator_name,
                    assigned_staff, participants,
                    closed_by_id, first_staff_response_at, panel_message_id,
                    staff_note, close_reason, reopen_history,
                    timeout_frozen, metadata
                ) VALUES (
                    $1,  $2,  $3,  $4,
                    $5,  $6,  $7,
                    $8,  $9,  $10,
                    $11, $12,
                    $13, $14, $15,
                    $16, $17, $18::jsonb,
                    $19, $20::jsonb
                )
                ON CONFLICT DO NOTHING
                """,
                ticket_id,
                int(doc.get("guild_id") or 0),
                doc.get("ticket_type") or "",
                status,
                _to_dt(doc.get("created_at")) or datetime.now(timezone.utc),
                _to_dt(doc.get("closed_at")),
                _to_dt(doc.get("last_message_at")),
                int(doc["channel_id"]) if doc.get("channel_id") is not None else None,
                int(creator.get("id") or 0),
                creator.get("display_name") or "",
                assigned_staff,
                participants,
                int(doc["closed_by_id"]) if doc.get("closed_by_id") is not None else None,
                _to_dt(doc.get("first_staff_response_at")),
                int(doc["panel_message_id"]) if doc.get("panel_message_id") is not None else None,
                doc.get("staff_note"),
                doc.get("close_reason"),
                _dumps(reopen_history),
                bool(doc.get("timeout_frozen") or False),
                _dumps(metadata),
            )
            migrated += 1
        except Exception as exc:
            logger.warning("tickets skip {}: {}", ticket_id, exc)
            skipped += 1

    # Reset SERIAL sequence so new tickets don't collide
    if migrated:
        await pg.execute(
            "SELECT setval('tickets_ticket_id_seq', COALESCE((SELECT MAX(ticket_id) FROM tickets), 1))"
        )
        logger.info("tickets: sequence reset to MAX(ticket_id)")

    logger.info("tickets: migrated={} skipped={}", migrated, skipped)
    return migrated


# ---------------------------------------------------------------------------
# 10. transcripts (FK → tickets)
# ---------------------------------------------------------------------------


def _map_transcript_entry(entry: dict[str, Any]) -> dict[str, Any]:
    ts = entry.get("timestamp")
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts = ts.isoformat()
    attachments = []
    for att in entry.get("attachments") or []:
        if isinstance(att, dict):
            attachments.append(
                {
                    "filename": att.get("filename"),
                    "url": att.get("url"),
                    "size": att.get("size"),
                    "content_type": att.get("content_type"),
                }
            )
    return {
        "message_id": entry.get("message_id"),
        "author_id": entry.get("author_id"),
        "author_display_name": entry.get("author_display_name"),
        "author_avatar_url": entry.get("author_avatar_url"),
        "author_is_bot": entry.get("author_is_bot", False),
        "content": entry.get("content") or "",
        "timestamp": ts,
        "attachments": attachments,
        # author_name, edited_at, embeds intentionally dropped
    }


async def migrate_transcripts(db: Any, pg: asyncpg.Connection) -> int:
    migrated = skipped = 0
    async for doc in db["transcripts"].find({}):
        ticket_id = doc.get("ticket_id")
        if ticket_id is None:
            skipped += 1
            continue
        ticket_id = int(ticket_id)
        raw_entries = doc.get("entries") or []
        entries = [_map_transcript_entry(e) for e in raw_entries]
        try:
            await pg.execute(
                """
                INSERT INTO transcripts (ticket_id, entries)
                VALUES ($1, $2::jsonb)
                ON CONFLICT DO NOTHING
                """,
                ticket_id,
                _dumps(entries),
            )
            migrated += 1
        except Exception as exc:
            logger.warning("transcripts skip {}: {}", ticket_id, exc)
            skipped += 1
    logger.info("transcripts: migrated={} skipped={}", migrated, skipped)
    return migrated


# ---------------------------------------------------------------------------
# 11. survey_responses (FK → tickets + survey_templates)
# Only completed responses.
# ---------------------------------------------------------------------------


async def migrate_survey_responses(db: Any, pg: asyncpg.Connection) -> int:
    migrated = skipped = 0
    async for doc in db["survey_responses"].find({"completed": True}):
        ticket_id = doc.get("ticket_id")
        template_id = doc.get("template_id")
        if ticket_id is None or template_id is None:
            skipped += 1
            continue
        ticket_id = int(ticket_id)
        responses = doc.get("answers") or doc.get("responses") or {}
        submitted_at = _to_dt(doc.get("completed_at") or doc.get("submitted_at"))
        try:
            await pg.execute(
                """
                INSERT INTO survey_responses (ticket_id, template_id, responses, submitted_at)
                VALUES ($1, $2, $3::jsonb, $4)
                ON CONFLICT DO NOTHING
                """,
                ticket_id,
                str(template_id),
                _dumps(responses),
                submitted_at,
            )
            migrated += 1
        except Exception as exc:
            logger.warning("survey_responses skip {}: {}", ticket_id, exc)
            skipped += 1
    logger.info("survey_responses: migrated={} skipped={}", migrated, skipped)
    return migrated


# ---------------------------------------------------------------------------
# 12. role_panels (added via migration 0002)
# ---------------------------------------------------------------------------


async def migrate_role_panels(db: Any, pg: asyncpg.Connection) -> int:
    migrated = skipped = 0
    async for doc in db["role_panels"].find({}):
        panel_id = doc.get("panel_id") or str(doc["_id"])
        roles = [
            {
                "role_id": r.get("role_id"),
                "label": r.get("label"),
                "description": r.get("description"),
                "emoji": r.get("emoji"),
            }
            for r in (doc.get("roles") or [])
        ]
        try:
            await pg.execute(
                """
                INSERT INTO role_panels (
                    panel_id, guild_id, channel_id, message_id,
                    title, description, max_selectable, roles,
                    created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
                ON CONFLICT DO NOTHING
                """,
                panel_id,
                int(doc.get("guild_id") or 0),
                int(doc.get("channel_id") or 0),
                int(doc.get("message_id") or 0),
                doc.get("title") or "",
                doc.get("description") or "",
                int(doc["max_selectable"]) if doc.get("max_selectable") is not None else None,
                _dumps(roles),
                _to_dt(doc.get("created_at")) or datetime.now(timezone.utc),
                _to_dt(doc.get("updated_at")) or datetime.now(timezone.utc),
            )
            migrated += 1
        except Exception as exc:
            logger.warning("role_panels skip {}: {}", panel_id, exc)
            skipped += 1
    logger.info("role_panels: migrated={} skipped={}", migrated, skipped)
    return migrated


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


async def main() -> None:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set")

    mongo = AsyncMongoClient(MONGO_URI)
    db = mongo[MONGO_DB]
    pg = await asyncpg.connect(dsn=_pg_dsn(DATABASE_URL))

    try:
        logger.info("Starting MongoDB → PostgreSQL migration")
        logger.info("Mongo: {}/{}", MONGO_URI, MONGO_DB)

        await migrate_survey_templates(db, pg)
        await migrate_users(db, pg)

        # Build RSN → discord_user_id map once after users are inserted
        rsn_rows = await pg.fetch(
            "SELECT LOWER(rsn) AS rsn_lower, discord_user_id FROM users WHERE rsn IS NOT NULL"
        )
        rsn_map: dict[str, int] = {r["rsn_lower"]: r["discord_user_id"] for r in rsn_rows}
        logger.info("RSN map built: {} entries", len(rsn_map))

        await migrate_events(db, pg, rsn_map)
        await migrate_coffer_events(db, pg)
        await migrate_membership_events(db, pg)
        await migrate_leaderboards(db, pg)
        await migrate_metrics(db, pg)
        await migrate_config(db, pg)
        await migrate_tickets(db, pg)
        await migrate_transcripts(db, pg)
        await migrate_survey_responses(db, pg)
        await migrate_role_panels(db, pg)

        logger.info("Migration complete.")
    finally:
        await mongo.aclose()
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
