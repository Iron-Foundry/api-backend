from __future__ import annotations

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.dependencies import get_session, get_valkey, verify_clan
from app.models.clan_chat import ClanChatPayload
from app.services import parser
from app.services.ccingest_metrics import collector as ccingest_collector
from app.services.dispatcher import is_duplicate, publish
from app.services.parser import BroadcastType

from ._broadcast_achievements import handle_achievement, handle_pet
from ._broadcast_clan import (
    handle_clan_leave,
    handle_coffer,
    handle_hcim_death,
    handle_new_member,
)
from ._broadcast_loot import handle_clue_item, handle_loot, handle_loot_key
from ._broadcast_misc import (
    handle_league_area,
    handle_league_rank,
    handle_league_relic,
    handle_pk,
    handle_unknown,
)
from ._broadcast_stats import (
    handle_collection_log,
    handle_level_up,
    handle_personal_best,
    handle_xp_milestone,
)
from ._helpers import any_opted_out, broadcast_player_names, now

router = APIRouter()

_BROADCAST_HANDLERS = {
    BroadcastType.LOOT: handle_loot,
    BroadcastType.LOOT_KEY: handle_loot_key,
    BroadcastType.CLUE_ITEM: handle_clue_item,
    BroadcastType.LEVEL_UP: handle_level_up,
    BroadcastType.XP_MILESTONE: handle_xp_milestone,
    BroadcastType.COLLECTION_LOG: handle_collection_log,
    BroadcastType.PERSONAL_BEST: handle_personal_best,
    BroadcastType.QUEST: handle_achievement,
    BroadcastType.DIARY: handle_achievement,
    BroadcastType.COMBAT_ACHIEVEMENT: handle_achievement,
    BroadcastType.PET: handle_pet,
    BroadcastType.NEW_MEMBER: handle_new_member,
    BroadcastType.LEFT_CLAN: handle_clan_leave,
    BroadcastType.EXPELLED: handle_clan_leave,
    BroadcastType.COFFER_DONATION: handle_coffer,
    BroadcastType.COFFER_WITHDRAWAL: handle_coffer,
    BroadcastType.HCIM_DEATH: handle_hcim_death,
    BroadcastType.PK: handle_pk,
    BroadcastType.LEAGUE_RELIC: handle_league_relic,
    BroadcastType.LEAGUE_RANK: handle_league_rank,
    BroadcastType.LEAGUE_AREA: handle_league_area,
}


async def _handle_broadcast(
    payload: ClanChatPayload, clan: dict, session: AsyncSession, valkey: Valkey
) -> None:
    kind = parser.classify(payload.message)
    ccingest_collector.record(kind.value)

    if await any_opted_out(session, broadcast_player_names(kind, payload.message)):
        return

    ts = now()
    handler = _BROADCAST_HANDLERS.get(kind, handle_unknown)
    await handler(payload, clan, session, valkey, ts)


@router.post("/ccingest")
async def ingest_chat(
    payloads: list[ClanChatPayload],
    clan: dict = Depends(verify_clan),
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> dict:
    """Receive a batch of clan chat messages from the TrackScape Connector plugin."""
    for payload in payloads:
        is_broadcast = payload.sender == payload.clan_name

        if await is_duplicate(valkey, clan["key"], payload.sender, payload.message):
            logger.debug(
                "[{}] Duplicate payload from {}, skipping",
                clan["guild_id"],
                payload.sender,
            )
            ccingest_collector.record("duplicate")
            continue

        if is_broadcast:
            await _handle_broadcast(payload, clan, session, valkey)
        else:
            ccingest_collector.record("chat")
            await publish(
                valkey,
                "chat",
                {
                    "player_name": payload.sender,
                    "rank": payload.rank,
                    "raw_message": payload.message,
                    "timestamp": now().isoformat(),
                },
            )

    await session.execute(
        text(
            "UPDATE events e SET user_id = u.discord_user_id"
            " FROM (SELECT discord_user_id, lower(rsn) AS rsn_lower FROM user_accounts"
            "       UNION SELECT discord_user_id, lower(rsn) FROM users WHERE rsn IS NOT NULL) u"
            " WHERE replace(lower(e.player_name), chr(160), ' ') = u.rsn_lower AND e.user_id IS NULL"
        )
    )
    await session.execute(
        text(
            "UPDATE events e SET user_account_id = ua.id FROM user_accounts ua"
            " WHERE replace(lower(e.player_name), chr(160), ' ') = lower(ua.rsn) AND e.user_account_id IS NULL"
        )
    )
    await session.execute(
        text(
            "UPDATE coffer_events ce SET user_account_id = ua.id FROM user_accounts ua"
            " WHERE lower(ce.player_name) = lower(ua.rsn) AND ce.user_account_id IS NULL"
        )
    )
    await session.execute(
        text(
            "UPDATE membership_events me SET user_account_id = ua.id FROM user_accounts ua"
            " WHERE lower(me.player_name) = lower(ua.rsn) AND me.user_account_id IS NULL"
        )
    )
    await session.commit()
    return {"ok": True, "processed": len(payloads)}
