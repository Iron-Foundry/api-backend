from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, User, UserAccount
from app.dependencies import get_current_user, get_session

router = APIRouter()


def _build_feed_item(
    row: Event, discord_user_id: int, rsn_lower_set: set[str]
) -> dict | None:
    d = row.data or {}
    ts = row.timestamp.isoformat()
    t = row.type
    if t == "loot":
        return {
            "type": "drop",
            "timestamp": ts,
            "label": d.get("item_name", ""),
            "detail": d.get("source"),
            "value": d.get("coin_value", 0),
        }
    if t == "level":
        skill = d.get("skill", "")
        return {
            "type": "level",
            "timestamp": ts,
            "label": "Total Level" if skill == "total" else skill,
            "detail": None,
            "value": d.get("new_level", 0),
        }
    if t == "xp_milestone":
        return {
            "type": "xp_milestone",
            "timestamp": ts,
            "label": d.get("skill", ""),
            "detail": None,
            "value": d.get("xp", 0),
        }
    if t in ("quest", "diary", "combat_achievement"):
        return {
            "type": d.get("achievement_type", t),
            "timestamp": ts,
            "label": d.get("name", ""),
            "detail": None,
            "value": None,
        }
    if t == "pet":
        return {
            "type": "pet",
            "timestamp": ts,
            "label": "Pet drop!",
            "detail": None,
            "value": None,
        }
    if t == "collection_log":
        return {
            "type": "collection_log",
            "timestamp": ts,
            "label": d.get("item_name", ""),
            "detail": f"Slot {d.get('log_slots')}/{d.get('log_slots_max')}",
            "value": None,
        }
    if t == "clue_item":
        return {
            "type": "clue",
            "timestamp": ts,
            "label": d.get("item_name", ""),
            "detail": "Clue scroll",
            "value": d.get("coin_value", 0),
        }
    if t == "pk":
        won = (
            row.user_id == discord_user_id
            and (row.player_name or "").lower() in rsn_lower_set
        )
        other = d.get("loser" if won else "winner", "")
        return {
            "type": "pk",
            "timestamp": ts,
            "label": f"{'Killed' if won else 'Killed by'} {other}",
            "detail": None,
            "value": d.get("gp_exchanged", 0),
        }
    if t == "personal_best":
        return {
            "type": "personal_best",
            "timestamp": ts,
            "label": d.get("activity", ""),
            "detail": d.get("variant"),
            "value": d.get("time_seconds"),
        }
    if t == "hcim_death":
        return {
            "type": "hcim_death",
            "timestamp": ts,
            "label": "Died as HCIM",
            "detail": None,
            "value": None,
        }
    if t == "loot_key":
        return {
            "type": "loot_key",
            "timestamp": ts,
            "label": "Loot key opened",
            "detail": None,
            "value": d.get("coin_value", 0),
        }
    if t == "league_relic":
        return {
            "type": "league_relic",
            "timestamp": ts,
            "label": f"Tier {d.get('tier')} League relic",
            "detail": None,
            "value": None,
        }
    if t == "league_rank":
        return {
            "type": "league_rank",
            "timestamp": ts,
            "label": f"{d.get('rank', '')} rank",
            "detail": None,
            "value": None,
        }
    if t == "league_area":
        area = d.get("area_count")
        return {
            "type": "league_area",
            "timestamp": ts,
            "label": "Final League area" if area is None else f"League area {area}",
            "detail": None,
            "value": None,
        }
    if t == "unknown":
        return {
            "type": "unknown",
            "timestamp": ts,
            "label": row.raw_message or "Unknown event",
            "detail": None,
            "value": None,
        }
    if t == "name_change":
        return {
            "type": "name_change",
            "timestamp": ts,
            "label": f"{d.get('old_name', '')} -> {d.get('new_name', '')}",
            "detail": None,
            "value": None,
        }
    return {
        "type": t,
        "timestamp": ts,
        "label": d.get("name") or d.get("item_name") or t,
        "detail": None,
        "value": None,
    }


@router.get("/me/feed")
async def member_feed(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    discord_user_id = int(current_user["sub"])

    accounts_result = await session.execute(
        select(UserAccount.id, UserAccount.rsn).where(
            UserAccount.discord_user_id == discord_user_id
        )
    )
    account_rows = accounts_result.all()
    linked_rsns = [r.rsn for r in account_rows]
    linked_account_ids = [r.id for r in account_rows]

    if not linked_rsns:
        fallback = await session.execute(
            select(User.rsn).where(
                User.discord_user_id == discord_user_id, User.rsn.isnot(None)
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

    event_conditions = [
        Event.user_id == discord_user_id,
        func.replace(func.lower(Event.player_name), "\xa0", " ").in_(rsn_lower_list),
    ]
    if linked_account_ids:
        event_conditions.append(Event.user_account_id.in_(linked_account_ids))
    events_result = await session.execute(
        select(Event)
        .where(or_(*event_conditions))
        .order_by(Event.timestamp.desc())
        .limit(fetch_limit)
    )
    rows = events_result.scalars().all()

    pk_conditions: list = [
        func.lower(Event.data["loser"].as_string()).in_(list(rsn_lower_set)),
        Event.user_id != discord_user_id,
    ]
    if linked_account_ids:
        pk_conditions = [
            or_(
                func.lower(Event.data["loser"].as_string()).in_(list(rsn_lower_set)),
                Event.user_account_id.in_(linked_account_ids),
            ),
            Event.user_id != discord_user_id,
        ]
    pk_result = await session.execute(
        select(Event)
        .where(Event.type == "pk", *pk_conditions)
        .order_by(Event.timestamp.desc())
        .limit(fetch_limit)
    )
    pk_rows = pk_result.scalars().all()

    unknown_conditions = [
        func.lower(
            func.left(func.regexp_replace(Event.raw_message, r"^<img=\d+>\s*", ""), 12)
        ).contains(rsn.lower())
        for rsn in linked_rsns
    ]
    unknown_rows: list[Event] = []
    if unknown_conditions:
        unknown_result = await session.execute(
            select(Event)
            .where(Event.type == "unknown", or_(*unknown_conditions))
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
        item = _build_feed_item(row, discord_user_id, rsn_lower_set)
        if item is not None:
            item["rsn"] = row.player_name or None
            items.append(item)
    items.sort(key=lambda x: x["timestamp"], reverse=True)  # type: ignore[index]
    return items[skip : skip + limit]
