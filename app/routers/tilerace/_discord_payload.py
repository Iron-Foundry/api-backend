from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import TileRaceEvent, TileRaceSignup, TileRaceTeam

from ._discord_perms import normalize as normalize_perms

COMMAND_CHANNEL = "foundry:tilerace_discord"


class DiscordTeamResult(BaseModel):
    team_id: int
    role_id: int | None = None
    text_channel_id: int | None = None
    voice_channel_id: int | None = None


class DiscordProvisionResult(BaseModel):
    category_id: int | None = None
    captains_role_id: int | None = None
    captains_channel_id: int | None = None
    submissions_channel_id: int | None = None
    teams: list[DiscordTeamResult] = []


async def build_command(
    session: AsyncSession, event: TileRaceEvent, action: str
) -> dict[str, Any]:
    """Describe an event's teams for the bot to provision, rename, or delete.

    The bot holds no tile race state of its own, so every command carries the
    full desired shape rather than a diff. Ids already assigned are echoed back
    so a rename can find the objects it needs to edit.
    """
    teams = (
        (
            await session.execute(
                select(TileRaceTeam)
                .where(TileRaceTeam.event_id == event.id)
                .order_by(TileRaceTeam.id)
            )
        )
        .scalars()
        .all()
    )
    captains = (
        (
            await session.execute(
                select(TileRaceSignup).where(
                    TileRaceSignup.event_id == event.id,
                    TileRaceSignup.is_captain.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    rosters: dict[int, list[str]] = {}
    for signup in (
        (
            await session.execute(
                select(TileRaceSignup).where(
                    TileRaceSignup.event_id == event.id,
                    TileRaceSignup.team_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    ):
        rosters.setdefault(int(signup.team_id or 0), []).append(
            str(signup.discord_user_id)
        )
    return {
        "action": action,
        "event_id": str(event.id),
        "event_name": event.name,
        "category_id": _opt(event.discord_category_id),
        "captains_role_id": _opt(event.discord_captains_role_id),
        "captains_channel_id": _opt(event.discord_captains_channel_id),
        "submissions_channel_id": _opt(event.discord_submissions_channel_id),
        "captain_user_ids": [str(c.discord_user_id) for c in captains],
        "permissions": normalize_perms(event.discord_permissions),
        "teams": [
            {
                "team_id": str(t.id),
                "name": t.name,
                "slug": t.slug,
                "role_id": _opt(t.discord_role_id),
                "text_channel_id": _opt(t.discord_text_channel_id),
                "voice_channel_id": _opt(t.discord_voice_channel_id),
                "member_user_ids": rosters.get(t.id, []),
            }
            for t in teams
        ],
    }


def _opt(value: int | None) -> str | None:
    return str(value) if value is not None else None


async def publish(valkey: Valkey, command: dict[str, Any]) -> None:
    await valkey.publish(COMMAND_CHANNEL, json.dumps(command))


async def remove_team_objects(
    valkey: Valkey, event: TileRaceEvent, team: TileRaceTeam
) -> bool:
    """Delete one team's role and channels, leaving the rest of the event alone.

    A plain sync cannot do this: it only ever creates or renames, so a deleted
    team's objects would linger in the guild with nothing pointing at them.
    """
    if event.discord_category_id is None:
        return False
    await publish(
        valkey,
        {
            "action": "teardown_team",
            "event_id": str(event.id),
            "event_name": event.name,
            "team": {
                "team_id": str(team.id),
                "role_id": _opt(team.discord_role_id),
                "text_channel_id": _opt(team.discord_text_channel_id),
                "voice_channel_id": _opt(team.discord_voice_channel_id),
            },
        },
    )
    return True


async def sync_if_provisioned(
    session: AsyncSession, valkey: Valkey, event_id: int
) -> bool:
    """Push the current shape to Discord when this event has channels.

    Called after anything that changes a roster or a name. Discord is only ever
    told the full desired state, so an extra sync is harmless and a missed one
    leaves someone holding a role for a team they already left.
    """
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None or event.discord_category_id is None:
        return False
    await publish(valkey, await build_command(session, event, "sync"))
    return True
