from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import cast

from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CofferEvent, Event, MembershipEvent, User, UserAccount
from app.services.http import WiseOldManHandler, WomPriority

_DISCORD_BOT_TOKEN = os.getenv("DISCORD_SERVER_TOKEN", "")
_GUILD_ID = os.getenv("GUILD_ID", "")
_DISCORD_API = "https://discord.com/api"
_WOM_API_KEY = os.getenv("WOM_API_KEY")

_REFERRAL_SOURCES = {
    "reddit", "osrs_discord", "website", "recruited_by",
    "instagram", "other", "prefer_not_to_say",
}

_RSN_RE = re.compile(r"^[A-Za-z0-9 _-]{1,12}$")
_ACCOUNT_CAP = 5
_CAP_MSG = (
    "Account limit reached."
    " Manage your linked accounts at ironfoundry.cc/members/settings."
)


class PrivacyUpdate(BaseModel):
    stats_opt_out: bool | None = None
    hide_presence_notifications: bool | None = None


class RsnUpdate(BaseModel):
    rsn: str


class AddAccount(BaseModel):
    rsn: str


class ReferralUpdate(BaseModel):
    source: str
    detail: str | None = None


async def _upsert_primary_account(
    session: AsyncSession, discord_user_id: int, rsn: str
) -> None:
    """Demote current primary to alt and set rsn as the new primary. Does NOT commit."""
    now = datetime.now(timezone.utc)
    await session.execute(
        update(UserAccount)
        .where(UserAccount.discord_user_id == discord_user_id, UserAccount.is_primary == True)  # noqa: E712
        .values(is_primary=False)
    )
    existing = await session.execute(
        select(UserAccount.id).where(
            UserAccount.discord_user_id == discord_user_id,
            func.lower(UserAccount.rsn) == rsn.lower(),
        )
    )
    if existing.scalar_one_or_none():
        await session.execute(
            update(UserAccount)
            .where(UserAccount.discord_user_id == discord_user_id, func.lower(UserAccount.rsn) == rsn.lower())
            .values(is_primary=True)
        )
    else:
        await session.execute(pg_insert(UserAccount).values(
            discord_user_id=discord_user_id, rsn=rsn, is_primary=True, created_at=now,
        ))
    await session.execute(
        update(User).where(User.discord_user_id == discord_user_id).values(rsn=rsn, updated_at=now)
    )


async def _wom_link_rsn(
    session: AsyncSession,
    discord_user_id: int,
    rsn: str,
    ua_id: int | None,
) -> list[str]:
    """Fetch WOM name history, persist it, backfill event FKs. Returns all RSNs (current + history)."""
    all_rsns = [rsn]
    if ua_id is None:
        return all_rsns
    try:
        async with WiseOldManHandler(api_key=_WOM_API_KEY, priority=WomPriority.LOW) as wom:
            name_changes = await wom.get_player_name_changes(rsn)
        history = [c["oldName"] for c in name_changes if c.get("status") == "approved"]
        if history:
            await session.execute(
                update(UserAccount).where(UserAccount.id == ua_id).values(rsn_history=history)
            )
            all_rsns = [rsn] + history
    except Exception as exc:
        logger.warning("members: failed to fetch WOM name history for {!r}: {}", rsn, exc)

    lower_rsns = [r.lower() for r in all_rsns]
    event_result = await session.execute(
        update(Event)
        .where(func.replace(func.lower(Event.player_name), "\xa0", " ").in_(lower_rsns))
        .values(user_id=discord_user_id, user_account_id=ua_id)
    )
    await session.execute(
        update(CofferEvent)
        .where(func.lower(CofferEvent.player_name).in_(lower_rsns))
        .values(user_account_id=ua_id)
    )
    await session.execute(
        update(MembershipEvent)
        .where(func.lower(MembershipEvent.player_name).in_(lower_rsns))
        .values(user_account_id=ua_id)
    )
    logger.info(
        "members: linked user_id {} to {} event rows (history: {})",
        discord_user_id,
        cast(CursorResult, event_result).rowcount,
        len(all_rsns) - 1,
    )
    return all_rsns
