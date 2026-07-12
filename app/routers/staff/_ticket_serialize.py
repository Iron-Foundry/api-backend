from __future__ import annotations

from datetime import date, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Ticket, User

_BOGUS_DATE = date(2026, 4, 14)


def _is_bogus(created_at) -> bool:
    return (
        created_at is not None
        and created_at.astimezone(timezone.utc).date() == _BOGUS_DATE
    )


async def _load_user_map(
    ids: set[int], session: AsyncSession
) -> dict[int, Any]:
    if not ids:
        return {}
    rows = await session.execute(
        select(
            User.discord_user_id,
            User.discord_username,
            User.rsn,
            User.discord_avatar_url,
        ).where(User.discord_user_id.in_(ids))
    )
    return {row.discord_user_id: row for row in rows}


def _staff_ref(user_id: int | None, user_map: dict[int, Any]) -> dict | None:
    if user_id is None:
        return None
    u = user_map.get(user_id)
    return {
        "id": user_id,
        "display_name": (u.rsn or u.discord_username) if u else str(user_id),
        "avatar_url": u.discord_avatar_url if u else None,
    }


async def _load_transcript_timestamps(
    ticket_rows: list[Ticket], session: AsyncSession
) -> dict[int, dict[str, str | None]]:
    needs = {
        row.ticket_id
        for row in ticket_rows
        if (row.status == "closed" and row.closed_at is None)
        or _is_bogus(row.created_at)
    }
    if not needs:
        return {}
    ts_rows = await session.execute(
        text(
            "SELECT ticket_id,"
            " entries->0->>'timestamp' AS first_ts,"
            " entries->-1->>'timestamp' AS last_ts"
            " FROM transcripts WHERE ticket_id = ANY(:ids)"
        ),
        {"ids": list(needs)},
    )
    return {
        r.ticket_id: {"first_ts": r.first_ts, "last_ts": r.last_ts} for r in ts_rows
    }


async def serialize_tickets(
    ticket_rows: list[Ticket], session: AsyncSession
) -> list[dict]:
    """Resolve staff identities and transcript-derived timestamps for tickets."""
    staff_ids: set[int] = set()
    for row in ticket_rows:
        staff_ids.add(row.creator_id)
        if row.closed_by_id is not None:
            staff_ids.add(row.closed_by_id)
        staff_ids.update(row.participants or [])

    user_map = await _load_user_map(staff_ids, session)
    transcript_ts_map = await _load_transcript_timestamps(ticket_rows, session)

    tickets: list[dict] = []
    for row in ticket_rows:
        creator = user_map.get(row.creator_id)
        td = transcript_ts_map.get(row.ticket_id, {})
        created_at = (
            td.get("first_ts") or row.created_at.isoformat()
            if _is_bogus(row.created_at)
            else (row.created_at.isoformat() if row.created_at else None)
        )
        tickets.append(
            {
                "ticket_id": row.ticket_id,
                "guild_id": row.guild_id,
                "ticket_type": row.ticket_type,
                "status": row.status,
                "created_at": created_at,
                "closed_at": row.closed_at.isoformat()
                if row.closed_at
                else td.get("last_ts"),
                "last_message_at": row.last_message_at.isoformat()
                if row.last_message_at
                else None,
                "first_staff_response_at": row.first_staff_response_at.isoformat()
                if row.first_staff_response_at
                else None,
                "creator": {
                    "id": row.creator_id,
                    "display_name": row.creator_name,
                    "avatar_url": creator.discord_avatar_url if creator else None,
                    "rsn": creator.rsn if creator else None,
                },
                "closed_by": _staff_ref(row.closed_by_id, user_map),
                "participants": [
                    ref
                    for sid in (row.participants or [])
                    if (ref := _staff_ref(sid, user_map)) is not None
                ],
                "close_reason": row.close_reason,
                "staff_note": row.staff_note,
            }
        )
    return tickets
