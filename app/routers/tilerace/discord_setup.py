from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import TileRaceTeam
from app.dependencies import get_session, get_valkey, verify_metrics_key
from app.services.page_permissions import require_page_permission

from ._discord_payload import (
    DiscordProvisionResult,
    build_command,
    publish,
    sync_if_provisioned,
)
from ._discord_perms import normalize as normalize_perms
from ._roster_helpers import event_or_404
from .schemas import DiscordPermissionsPatch

router = APIRouter()
_PERM = Depends(require_page_permission("tilerace.admin", "edit"))


@router.post("/events/{event_id}/discord/setup")
async def setup_discord(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Ask discord-server to build the category, roles and per-team channels."""
    event = await event_or_404(session, event_id)
    if event.discord_category_id is not None:
        raise HTTPException(
            409, "Discord channels already exist. Tear them down first."
        )
    teams = (
        await session.execute(
            select(TileRaceTeam.id).where(TileRaceTeam.event_id == event_id)
        )
    ).all()
    if not teams:
        raise HTTPException(409, "Generate teams before setting up Discord.")
    await publish(valkey, await build_command(session, event, "setup"))
    return {"ok": True, "queued": "setup", "team_count": len(teams)}


@router.post("/events/{event_id}/discord/teardown")
async def teardown_discord(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Ask discord-server to delete everything it created for this event."""
    event = await event_or_404(session, event_id)
    if event.discord_category_id is None:
        raise HTTPException(409, "Nothing has been set up for this event.")
    await publish(valkey, await build_command(session, event, "teardown"))
    return {"ok": True, "queued": "teardown"}


@router.post("/events/{event_id}/discord/sync")
async def sync_discord(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Push current team names onto the existing roles and channels."""
    event = await event_or_404(session, event_id)
    if event.discord_category_id is None:
        raise HTTPException(409, "Nothing has been set up for this event.")
    await publish(valkey, await build_command(session, event, "sync"))
    return {"ok": True, "queued": "sync"}


@router.patch("/events/{event_id}/discord/permissions")
async def patch_discord_permissions(
    event_id: int,
    body: DiscordPermissionsPatch,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Toggle the elevated permissions teams hold in their own channels.

    The toggles are applied by the following sync, which edits the overwrite on
    the existing channels: nothing is torn down and no channel is recreated, so
    a live event keeps its history.
    """
    event = await event_or_404(session, event_id)
    perms = normalize_perms(event.discord_permissions)
    perms.update(body.model_dump(exclude_unset=True, exclude_none=True))
    event.discord_permissions = perms
    event.updated_at = datetime.now(UTC)
    await session.commit()
    return {
        "ok": True,
        "discord_permissions": perms,
        "synced": await sync_if_provisioned(session, valkey, event_id),
    }


@router.post("/events/{event_id}/discord/result")
async def record_discord_result(
    event_id: int,
    body: DiscordProvisionResult,
    session: AsyncSession = Depends(get_session),
    _key: None = Depends(verify_metrics_key),
) -> dict[str, Any]:
    """Service-key callback: discord-server reports the ids it created or cleared.

    A teardown reports every id as null, which is what clears them here.
    """
    event = await event_or_404(session, event_id)
    event.discord_category_id = body.category_id
    event.discord_captains_role_id = body.captains_role_id
    event.discord_captains_channel_id = body.captains_channel_id
    event.updated_at = datetime.now(UTC)
    by_id = {t.team_id: t for t in body.teams}
    teams = (
        (
            await session.execute(
                select(TileRaceTeam).where(TileRaceTeam.event_id == event_id)
            )
        )
        .scalars()
        .all()
    )
    for team in teams:
        result = by_id.get(team.id)
        team.discord_role_id = result.role_id if result else None
        team.discord_text_channel_id = result.text_channel_id if result else None
        team.discord_voice_channel_id = result.voice_channel_id if result else None
        team.updated_at = datetime.now(UTC)
    await session.commit()
    return {"ok": True, "teams_recorded": len(by_id)}
