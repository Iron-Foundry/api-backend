"""Members router - authenticated endpoints for profile self-management."""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from typing import cast

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, PlayerRanking, Ticket, User, UserAccount
from app.dependencies import get_current_user, get_session
from app.services.rsn_cascade import backfill_user_from_rsn

_DISCORD_BOT_TOKEN = os.getenv("DISCORD_SERVER_TOKEN", "")
_GUILD_ID = os.getenv("GUILD_ID", "")
_DISCORD_API = "https://discord.com/api"

_REFERRAL_SOURCES = {
    "reddit",
    "osrs_discord",
    "website",
    "recruited_by",
    "instagram",
    "other",
    "prefer_not_to_say",
}

router = APIRouter(prefix="/members", tags=["members"])

_RSN_RE = re.compile(r"^[A-Za-z0-9 _-]{1,12}$")


class PrivacyUpdate(BaseModel):
    stats_opt_out: bool | None = None
    hide_presence_notifications: bool | None = None


class RsnUpdate(BaseModel):
    rsn: str


class AddAccount(BaseModel):
    rsn: str


_ACCOUNT_CAP = 5
_CAP_MSG = (
    "Account limit reached."
    " Manage your linked accounts at ironfoundry.cc/members/settings."
)


async def _upsert_primary_account(
    session: AsyncSession, discord_user_id: int, rsn: str
) -> None:
    """Demote the current primary to alt and set rsn as the new primary.

    Also updates users.rsn cache. Does NOT commit.
    """
    now = datetime.now(timezone.utc)

    # Demote existing primary
    await session.execute(
        update(UserAccount)
        .where(
            UserAccount.discord_user_id == discord_user_id,
            UserAccount.is_primary == True,  # noqa: E712
        )
        .values(is_primary=False)
    )

    # Does this RSN already exist for the user?
    existing = await session.execute(
        select(UserAccount.id).where(
            UserAccount.discord_user_id == discord_user_id,
            func.lower(UserAccount.rsn) == rsn.lower(),
        )
    )
    if existing.scalar_one_or_none():
        await session.execute(
            update(UserAccount)
            .where(
                UserAccount.discord_user_id == discord_user_id,
                func.lower(UserAccount.rsn) == rsn.lower(),
            )
            .values(is_primary=True)
        )
    else:
        await session.execute(
            pg_insert(UserAccount).values(
                discord_user_id=discord_user_id,
                rsn=rsn,
                is_primary=True,
                created_at=now,
            )
        )

    # Sync cache
    await session.execute(
        update(User)
        .where(User.discord_user_id == discord_user_id)
        .values(rsn=rsn, updated_at=now)
    )


@router.patch("/me/privacy")
async def update_privacy(
    body: PrivacyUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Toggle stats opt-out for the authenticated user."""
    discord_user_id = int(current_user["sub"])
    values: dict = {"updated_at": datetime.now(timezone.utc)}
    if body.stats_opt_out is not None:
        values["stats_opt_out"] = body.stats_opt_out
    if body.hide_presence_notifications is not None:
        values["hide_presence_notifications"] = body.hide_presence_notifications
    if len(values) == 1:
        return {}
    await session.execute(
        update(User).where(User.discord_user_id == discord_user_id).values(**values)
    )
    await session.commit()
    logger.info("members/privacy: user {} updated privacy {}", discord_user_id, values)
    return {k: v for k, v in values.items() if k != "updated_at"}


@router.patch("/me/rsn")
async def update_rsn(
    body: RsnUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update the RSN linked to the authenticated user's account."""
    rsn = body.rsn.strip()
    if not rsn:
        raise HTTPException(status_code=422, detail="RSN cannot be empty.")
    if not _RSN_RE.match(rsn):
        raise HTTPException(
            status_code=422,
            detail="RSN must be 1–12 characters: letters, numbers, spaces, hyphens, underscores.",
        )

    discord_user_id = int(current_user["sub"])

    # Global uniqueness check via user_accounts
    conflict_result = await session.execute(
        select(UserAccount.discord_user_id).where(
            func.lower(UserAccount.rsn) == rsn.lower()
        )
    )
    conflict = conflict_result.scalar_one_or_none()
    if conflict and conflict != discord_user_id:
        raise HTTPException(
            status_code=409, detail="That RSN is linked to another account."
        )

    # Cap check: this will add/promote an RSN, so count non-owned slots
    if not conflict:
        cap_result = await session.execute(
            select(func.count())
            .select_from(UserAccount)
            .where(UserAccount.discord_user_id == discord_user_id)
        )
        if (cap_result.scalar_one() or 0) >= _ACCOUNT_CAP:
            raise HTTPException(status_code=422, detail=_CAP_MSG)

    await _upsert_primary_account(session, discord_user_id, rsn)
    logger.info("members/rsn: user {} set primary RSN {!r}", discord_user_id, rsn)

    user_result = await session.execute(
        select(User.clan_rank, User.total_loot_value, User.collection_log_slots).where(
            User.discord_user_id == discord_user_id
        )
    )
    user_row = user_result.one_or_none()

    backfill = await backfill_user_from_rsn(
        session,
        discord_user_id,
        rsn,
        clan_rank=user_row.clan_rank if user_row else None,
        total_loot_value=user_row.total_loot_value if user_row else 0,
        collection_log_slots=user_row.collection_log_slots if user_row else 0,
    )
    if backfill:
        logger.info(
            "members/rsn: backfilled fields {} for user {}",
            list(backfill.keys()),
            discord_user_id,
        )

    event_result = await session.execute(
        update(Event)
        .where(func.replace(func.lower(Event.player_name), "\xa0", " ") == rsn.lower())
        .values(user_id=discord_user_id)
    )
    logger.info(
        "members/rsn: linked user_id {} to {} event rows",
        discord_user_id,
        cast(CursorResult, event_result).rowcount,
    )

    await session.commit()
    return {"rsn": rsn}


@router.get("/me/feed")
async def member_feed(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return a personal activity feed for the authenticated user, keyed by their linked RSN.

    All event types are included with no value filters. The `limit` most recent
    events across all collections are returned, sorted by timestamp descending.
    """
    discord_user_id = int(current_user["sub"])

    accounts_result = await session.execute(
        select(UserAccount.rsn).where(UserAccount.discord_user_id == discord_user_id)
    )
    linked_rsns = [r.rsn for r in accounts_result.all()]
    if not linked_rsns:
        # Fall back to users.rsn for accounts predating the user_accounts table.
        fallback = await session.execute(
            select(User.rsn).where(
                User.discord_user_id == discord_user_id,
                User.rsn.isnot(None),
            )
        )
        primary_rsn = fallback.scalar_one_or_none()
        if primary_rsn:
            linked_rsns = [primary_rsn]
        else:
            return []

    rsn_lower_set = {r.lower() for r in linked_rsns}
    rsn_lower_list = list(rsn_lower_set)

    fetch_limit = min(limit * 10, 2000)
    events_result = await session.execute(
        select(Event)
        .where(
            or_(
                Event.user_id == discord_user_id,
                func.replace(func.lower(Event.player_name), "\xa0", " ").in_(
                    rsn_lower_list
                ),
            )
        )
        .order_by(Event.timestamp.desc())
        .limit(fetch_limit)
    )
    rows = events_result.scalars().all()

    pk_result = await session.execute(
        select(Event)
        .where(
            Event.type == "pk",
            func.lower(Event.data["loser"].as_string()).in_(list(rsn_lower_set)),
            Event.user_id != discord_user_id,
        )
        .order_by(Event.timestamp.desc())
        .limit(fetch_limit)
    )
    pk_rows = pk_result.scalars().all()

    unknown_conditions = [
        func.lower(
            func.left(
                func.regexp_replace(Event.raw_message, r"^<img=\d+>\s*", ""),
                12,  # max OSRS RSN length
            )
        ).contains(rsn.lower())
        for rsn in linked_rsns
    ]
    unknown_rows: list[Event] = []
    if unknown_conditions:
        unknown_result = await session.execute(
            select(Event)
            .where(
                Event.type == "unknown",
                or_(*unknown_conditions),
            )
            .order_by(Event.timestamp.desc())
            .limit(fetch_limit)
        )
        unknown_rows = list(unknown_result.scalars().all())

    seen_ids: set[int] = set()
    all_rows: list[Event] = []
    for row in list(rows) + list(pk_rows) + unknown_rows:
        if row.id not in seen_ids:
            seen_ids.add(row.id)
            all_rows.append(row)

    items: list[dict] = []
    for row in all_rows:
        d = row.data or {}
        ts = row.timestamp.isoformat()
        t = row.type

        if t == "loot":
            items.append(
                {
                    "type": "drop",
                    "timestamp": ts,
                    "label": d.get("item_name", ""),
                    "detail": d.get("source"),
                    "value": d.get("coin_value", 0),
                }
            )
        elif t == "level":
            skill = d.get("skill", "")
            items.append(
                {
                    "type": "level",
                    "timestamp": ts,
                    "label": "Total Level" if skill == "total" else skill,
                    "detail": None,
                    "value": d.get("new_level", 0),
                }
            )
        elif t == "xp_milestone":
            items.append(
                {
                    "type": "xp_milestone",
                    "timestamp": ts,
                    "label": d.get("skill", ""),
                    "detail": None,
                    "value": d.get("xp", 0),
                }
            )
        elif t in ("quest", "diary", "combat_achievement"):
            items.append(
                {
                    "type": d.get("achievement_type", t),
                    "timestamp": ts,
                    "label": d.get("name", ""),
                    "detail": None,
                    "value": None,
                }
            )
        elif t == "pet":
            items.append(
                {
                    "type": "pet",
                    "timestamp": ts,
                    "label": "Pet drop!",
                    "detail": None,
                    "value": None,
                }
            )
        elif t == "collection_log":
            items.append(
                {
                    "type": "collection_log",
                    "timestamp": ts,
                    "label": d.get("item_name", ""),
                    "detail": f"Slot {d.get('log_slots')}/{d.get('log_slots_max')}",
                    "value": None,
                }
            )
        elif t == "clue_item":
            items.append(
                {
                    "type": "clue",
                    "timestamp": ts,
                    "label": d.get("item_name", ""),
                    "detail": "Clue scroll",
                    "value": d.get("coin_value", 0),
                }
            )
        elif t == "pk":
            won = (
                row.user_id == discord_user_id
                and (row.player_name or "").lower() in rsn_lower_set
            )
            other = d.get("loser" if won else "winner", "")
            items.append(
                {
                    "type": "pk",
                    "timestamp": ts,
                    "label": f"{'Killed' if won else 'Killed by'} {other}",
                    "detail": None,
                    "value": d.get("gp_exchanged", 0),
                }
            )
        elif t == "personal_best":
            items.append(
                {
                    "type": "personal_best",
                    "timestamp": ts,
                    "label": d.get("activity", ""),
                    "detail": d.get("variant"),
                    "value": d.get("time_seconds"),
                }
            )
        elif t == "hcim_death":
            items.append(
                {
                    "type": "hcim_death",
                    "timestamp": ts,
                    "label": "Died as HCIM",
                    "detail": None,
                    "value": None,
                }
            )
        elif t == "loot_key":
            items.append(
                {
                    "type": "loot_key",
                    "timestamp": ts,
                    "label": "Loot key opened",
                    "detail": None,
                    "value": d.get("coin_value", 0),
                }
            )
        elif t == "league_relic":
            items.append(
                {
                    "type": "league_relic",
                    "timestamp": ts,
                    "label": f"Tier {d.get('tier')} League relic",
                    "detail": None,
                    "value": None,
                }
            )
        elif t == "league_rank":
            items.append(
                {
                    "type": "league_rank",
                    "timestamp": ts,
                    "label": f"{d.get('rank', '')} rank",
                    "detail": None,
                    "value": None,
                }
            )
        elif t == "league_area":
            area = d.get("area_count")
            items.append(
                {
                    "type": "league_area",
                    "timestamp": ts,
                    "label": "Final League area"
                    if area is None
                    else f"League area {area}",
                    "detail": None,
                    "value": None,
                }
            )
        elif t == "unknown":
            items.append(
                {
                    "type": "unknown",
                    "timestamp": ts,
                    "label": row.raw_message or "Unknown event",
                    "detail": None,
                    "value": None,
                }
            )
        elif t == "name_change":
            items.append(
                {
                    "type": "name_change",
                    "timestamp": ts,
                    "label": f"{d.get('old_name', '')} -> {d.get('new_name', '')}",
                    "detail": None,
                    "value": None,
                }
            )
        else:
            items.append(
                {
                    "type": t,
                    "timestamp": ts,
                    "label": d.get("name") or d.get("item_name") or t,
                    "detail": None,
                    "value": None,
                }
            )

    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return items[skip : skip + limit]


@router.get("/me/stats")
async def get_me_stats(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    discord_user_id = int(current_user["sub"])

    user_result = await session.execute(
        select(
            User.collection_log_slots,
            User.collection_log_slots_max,
            User.total_loot_value,
            User.rsn,
        ).where(User.discord_user_id == discord_user_id)
    )
    user_row = user_result.one_or_none()

    rank_tier: str | None = None
    if user_row and user_row.rsn:
        ranking_result = await session.execute(
            select(PlayerRanking.rank).where(PlayerRanking.rsn.ilike(user_row.rsn))
        )
        rank_tier = ranking_result.scalar_one_or_none()

    return {
        "collection_log_slots": user_row.collection_log_slots if user_row else 0,
        "collection_log_slots_max": user_row.collection_log_slots_max
        if user_row
        else 0,
        "total_loot_value": user_row.total_loot_value if user_row else 0,
        "rank_tier": rank_tier,
    }


@router.get("/me/tickets")
async def member_tickets(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return all tickets created by the authenticated user."""
    discord_user_id = int(current_user["sub"])
    result = await session.execute(
        select(Ticket)
        .where(Ticket.creator_id == discord_user_id)
        .order_by(Ticket.ticket_id.desc())
    )
    tickets: list[dict] = []
    for row in result.scalars():
        tickets.append(
            {
                "ticket_id": row.ticket_id,
                "ticket_type": row.ticket_type,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "closed_at": row.closed_at.isoformat() if row.closed_at else None,
                "last_message_at": row.last_message_at.isoformat()
                if row.last_message_at
                else None,
                "close_reason": row.close_reason,
            }
        )
    return tickets


@router.get("/me/tickets/{ticket_id}/transcript")
async def member_ticket_transcript(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the transcript for one of the authenticated user's tickets.

    The staff_note field is never returned. Returns 404 if the ticket doesn't
    belong to this user or has no transcript (e.g. sensitive ticket types).
    """
    from app.db.models import Transcript

    discord_user_id = int(current_user["sub"])

    ticket_result = await session.execute(
        select(Ticket.ticket_id).where(
            Ticket.ticket_id == ticket_id,
            Ticket.creator_id == discord_user_id,
        )
    )
    if not ticket_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Ticket not found.")

    tr_result = await session.execute(
        select(Transcript).where(Transcript.ticket_id == ticket_id)
    )
    tr = tr_result.scalar_one_or_none()
    if not tr:
        raise HTTPException(
            status_code=404, detail="Transcript not available for this ticket."
        )

    raw = tr.entries
    entries = raw.get("entries", []) if isinstance(raw, dict) else (raw or [])
    return {"ticket_id": tr.ticket_id, "entries": entries}


@router.get("/me/api-key")
async def get_api_key(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the authenticated user's current API key and metadata."""
    discord_user_id = int(current_user["sub"])
    result = await session.execute(
        select(User.api_key, User.key_is_active, User.key_created_at).where(
            User.discord_user_id == discord_user_id
        )
    )
    row = result.one_or_none()
    if not row or not row.api_key:
        return {"key": None, "is_active": False, "created_at": None}
    return {
        "key": row.api_key,
        "is_active": row.key_is_active,
        "created_at": row.key_created_at.isoformat() if row.key_created_at else None,
    }


@router.post("/me/api-key/rotate")
async def rotate_api_key(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Generate a new API key for the authenticated user, invalidating the previous one."""
    discord_user_id = int(current_user["sub"])
    new_key = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await session.execute(
        update(User)
        .where(User.discord_user_id == discord_user_id)
        .values(api_key=new_key, key_is_active=True, key_created_at=now, updated_at=now)
    )
    await session.commit()
    logger.info("members/api-key: user {} rotated API key", discord_user_id)
    return {"key": new_key, "is_active": True, "created_at": now.isoformat()}


# ── Account (multi-RSN) endpoints ─────────────────────────────────────────────


@router.get("/me/accounts")
async def list_accounts(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return all RSN accounts linked to the authenticated user."""
    discord_user_id = int(current_user["sub"])
    result = await session.execute(
        select(UserAccount)
        .where(UserAccount.discord_user_id == discord_user_id)
        .order_by(UserAccount.is_primary.desc(), UserAccount.created_at.asc())
    )
    return [
        {
            "id": row.id,
            "rsn": row.rsn,
            "is_primary": row.is_primary,
            "created_at": row.created_at.isoformat(),
        }
        for row in result.scalars()
    ]


@router.get("/me/rankings")
async def get_me_rankings(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return ranking data for all linked RSN accounts, primary first."""
    discord_user_id = int(current_user["sub"])
    result = await session.execute(
        select(
            UserAccount.rsn,
            UserAccount.is_primary,
            PlayerRanking.rank,
            PlayerRanking.points,
            PlayerRanking.boss_points,
            PlayerRanking.skill_points,
        )
        .outerjoin(
            PlayerRanking, func.lower(PlayerRanking.rsn) == func.lower(UserAccount.rsn)
        )
        .where(UserAccount.discord_user_id == discord_user_id)
        .order_by(UserAccount.is_primary.desc(), UserAccount.created_at.asc())
    )
    return [
        {
            "rsn": row.rsn,
            "is_primary": row.is_primary,
            "rank": row.rank,
            "points": row.points,
            "boss_points": row.boss_points,
            "skill_points": row.skill_points,
        }
        for row in result.all()
    ]


@router.post("/me/accounts", status_code=201)
async def add_account(
    body: AddAccount,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Link an additional RSN to the authenticated user's account."""
    rsn = body.rsn.strip()
    if not rsn:
        raise HTTPException(status_code=422, detail="RSN cannot be empty.")
    if not _RSN_RE.match(rsn):
        raise HTTPException(
            status_code=422,
            detail="RSN must be 1–12 characters: letters, numbers, spaces, hyphens, underscores.",
        )

    discord_user_id = int(current_user["sub"])

    # Global uniqueness check
    conflict_result = await session.execute(
        select(UserAccount.discord_user_id).where(
            func.lower(UserAccount.rsn) == rsn.lower()
        )
    )
    conflict_owner = conflict_result.scalar_one_or_none()
    if conflict_owner == discord_user_id:
        raise HTTPException(
            status_code=409, detail="That RSN is already linked to your account."
        )
    if conflict_owner is not None:
        raise HTTPException(
            status_code=409, detail="That RSN is linked to another account."
        )

    # Cap check
    cap_result = await session.execute(
        select(func.count())
        .select_from(UserAccount)
        .where(UserAccount.discord_user_id == discord_user_id)
    )
    current_count = cap_result.scalar_one() or 0
    if current_count >= _ACCOUNT_CAP:
        raise HTTPException(status_code=422, detail=_CAP_MSG)

    now = datetime.now(timezone.utc)
    is_first = current_count == 0
    new_row = UserAccount(
        discord_user_id=discord_user_id,
        rsn=rsn,
        is_primary=is_first,
        created_at=now,
    )
    session.add(new_row)
    await session.flush()  # populate new_row.id

    if is_first:
        await session.execute(
            update(User)
            .where(User.discord_user_id == discord_user_id)
            .values(rsn=rsn, updated_at=now)
        )

    user_result = await session.execute(
        select(User.clan_rank, User.total_loot_value, User.collection_log_slots).where(
            User.discord_user_id == discord_user_id
        )
    )
    user_row = user_result.one_or_none()

    await backfill_user_from_rsn(
        session,
        discord_user_id,
        rsn,
        clan_rank=user_row.clan_rank if user_row else None,
        total_loot_value=user_row.total_loot_value if user_row else 0,
        collection_log_slots=user_row.collection_log_slots if user_row else 0,
    )

    event_result = await session.execute(
        update(Event)
        .where(func.replace(func.lower(Event.player_name), "\xa0", " ") == rsn.lower())
        .values(user_id=discord_user_id)
    )
    logger.info(
        "members/accounts: user {} added RSN {!r}, linked {} events",
        discord_user_id,
        rsn,
        cast(CursorResult, event_result).rowcount,
    )

    await session.commit()
    return {
        "id": new_row.id,
        "rsn": new_row.rsn,
        "is_primary": new_row.is_primary,
        "created_at": new_row.created_at.isoformat(),
    }


@router.patch("/me/accounts/{account_id}/set-primary")
async def set_primary_account(
    account_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Promote the given account to primary."""
    discord_user_id = int(current_user["sub"])

    row_result = await session.execute(
        select(UserAccount).where(
            UserAccount.id == account_id,
            UserAccount.discord_user_id == discord_user_id,
        )
    )
    row = row_result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found.")

    if row.is_primary:
        return {"id": row.id, "rsn": row.rsn, "is_primary": True}

    now = datetime.now(timezone.utc)

    # Demote old primary
    await session.execute(
        update(UserAccount)
        .where(
            UserAccount.discord_user_id == discord_user_id,
            UserAccount.is_primary == True,  # noqa: E712
        )
        .values(is_primary=False)
    )
    # Promote new
    await session.execute(
        update(UserAccount).where(UserAccount.id == account_id).values(is_primary=True)
    )
    # Sync cache
    await session.execute(
        update(User)
        .where(User.discord_user_id == discord_user_id)
        .values(rsn=row.rsn, updated_at=now)
    )

    await session.commit()
    logger.info("members/accounts: user {} set primary {!r}", discord_user_id, row.rsn)
    return {"id": row.id, "rsn": row.rsn, "is_primary": True}


@router.delete("/me/accounts/{account_id}", status_code=204)
async def delete_account(
    account_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove a linked RSN account."""
    discord_user_id = int(current_user["sub"])

    row_result = await session.execute(
        select(UserAccount).where(
            UserAccount.id == account_id,
            UserAccount.discord_user_id == discord_user_id,
        )
    )
    row = row_result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found.")

    # Count how many accounts this user has
    count_result = await session.execute(
        select(func.count())
        .select_from(UserAccount)
        .where(UserAccount.discord_user_id == discord_user_id)
    )
    total = count_result.scalar_one() or 0

    if row.is_primary and total > 1:
        raise HTTPException(
            status_code=422,
            detail="Cannot delete primary account while other accounts are linked."
            " Set a different primary first.",
        )

    now = datetime.now(timezone.utc)
    if total == 1:
        await session.execute(
            update(User)
            .where(User.discord_user_id == discord_user_id)
            .values(rsn=None, updated_at=now)
        )

    await session.delete(row)
    await session.commit()
    logger.info("members/accounts: user {} removed RSN {!r}", discord_user_id, row.rsn)


class ReferralUpdate(BaseModel):
    source: str
    detail: str | None = None


@router.patch("/me/referral")
async def update_referral(
    body: ReferralUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Save how the user found the community. Only accepted once (ignored if already set)."""
    if body.source not in _REFERRAL_SOURCES:
        raise HTTPException(status_code=422, detail="Invalid referral source.")

    detail = body.detail.strip() if body.detail else None
    if body.source == "recruited_by" and not detail:
        raise HTTPException(status_code=422, detail="Recruiter name required.")
    if body.source == "other" and not detail:
        raise HTTPException(status_code=422, detail="Please describe how you found us.")

    discord_user_id = int(current_user["sub"])
    now = datetime.now(timezone.utc)
    await session.execute(
        update(User)
        .where(User.discord_user_id == discord_user_id, User.referral_source.is_(None))
        .values(referral_source=body.source, referral_detail=detail, updated_at=now)
    )
    await session.commit()
    logger.info("members/referral: user {} source={!r}", discord_user_id, body.source)
    return {"ok": True}


@router.get("/discord-members")
async def search_discord_members(
    q: str = Query(default="", max_length=100),
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """Search guild members by username prefix for the recruited-by autocomplete."""
    if not _DISCORD_BOT_TOKEN or not _GUILD_ID:
        return []

    query = q.strip()
    if not query:
        return []

    headers = {"Authorization": f"Bot {_DISCORD_BOT_TOKEN}"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_DISCORD_API}/guilds/{_GUILD_ID}/members/search",
                params={"query": query, "limit": 10},
                headers=headers,
            )
        if resp.status_code != 200:
            logger.warning("discord-members search failed: {}", resp.status_code)
            return []
        members = resp.json()
        return [
            {
                "discord_user_id": m["user"]["id"],
                "username": m["user"].get("global_name") or m["user"]["username"],
                "avatar": m["user"].get("avatar"),
            }
            for m in members
            if "user" in m
        ]
    except Exception as exc:
        logger.warning("discord-members search error: {}", exc)
        return []
