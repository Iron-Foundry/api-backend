from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.services import parser
from app.services.feed_event import insert_feed_event
from app.services.parser import BroadcastType

_PLAYER_NAME_PARSERS: dict[BroadcastType, Callable[[str], Any]] = {
    BroadcastType.LOOT: parser.parse_loot,
    BroadcastType.LEVEL_UP: parser.parse_level_up,
    BroadcastType.XP_MILESTONE: parser.parse_xp_milestone,
    BroadcastType.QUEST: parser.parse_achievement,
    BroadcastType.DIARY: parser.parse_achievement,
    BroadcastType.COMBAT_ACHIEVEMENT: parser.parse_achievement,
    BroadcastType.PET: parser.parse_pet,
    BroadcastType.NEW_MEMBER: parser.parse_new_member,
    BroadcastType.COLLECTION_LOG: parser.parse_collection_log,
    BroadcastType.LOOT_KEY: parser.parse_loot_key,
    BroadcastType.CLUE_ITEM: parser.parse_clue_item,
    BroadcastType.PERSONAL_BEST: parser.parse_personal_best,
    BroadcastType.LEFT_CLAN: parser.parse_clan_leave,
    BroadcastType.EXPELLED: parser.parse_clan_leave,
    BroadcastType.COFFER_DONATION: parser.parse_coffer_transaction,
    BroadcastType.COFFER_WITHDRAWAL: parser.parse_coffer_transaction,
    BroadcastType.HCIM_DEATH: parser.parse_hcim_death,
    BroadcastType.LEAGUE_RELIC: parser.parse_league_relic,
    BroadcastType.LEAGUE_RANK: parser.parse_league_rank,
    BroadcastType.LEAGUE_AREA: parser.parse_league_area,
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def dispatch_doc(event_type: str, player_name: str | None, data: dict) -> dict:
    result: dict = {"type": event_type, "timestamp": now().isoformat()}
    if player_name:
        result["player_name"] = player_name
    result.update(data)
    return result


def broadcast_player_names(kind: BroadcastType, message: str) -> list[str]:
    if kind == BroadcastType.PK:
        parsed = parser.parse_pk(message)
        return [parsed.winner, parsed.loser] if parsed else []
    parse_fn = _PLAYER_NAME_PARSERS.get(kind)
    if parse_fn:
        parsed = parse_fn(message)
        return [parsed.player_name] if parsed else []
    return []


async def any_opted_out(session: AsyncSession, player_names: list[str]) -> bool:
    if not player_names:
        return False
    result = await session.execute(
        select(User.discord_user_id).where(
            User.rsn.in_(player_names),
            User.stats_opt_out == True,  # noqa: E712
        )
    )
    return result.first() is not None


async def update_player_rank(
    session: AsyncSession, player_name: str, rank: str
) -> None:
    await session.execute(
        update(User)
        .where(func.lower(User.rsn) == player_name.lower(), User.clan_rank != rank)
        .values(clan_rank=rank, updated_at=now())
    )


async def increment_loot_value(
    session: AsyncSession, player_name: str, value: int
) -> None:
    await session.execute(
        update(User)
        .where(func.lower(User.rsn) == player_name.lower())
        .values(total_loot_value=User.total_loot_value + value, updated_at=now())
    )


async def insert_event(session: AsyncSession, **kwargs: Any) -> None:
    await insert_feed_event(session, **kwargs)
