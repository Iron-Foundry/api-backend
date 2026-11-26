"""The staff route that pulls a frenzy event's teams and dates from Wise Old Man."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyEvent, FrenzyTeam
from app.dependencies import get_session
from app.services.http import WiseOldManHandler
from app.services.page_permissions import require_page_permission

from ._constants import _WOM_API_KEY, _WOM_DISCORD_CONTACT

router = APIRouter()

_PERM = Depends(require_page_permission("frenzy.admin", "edit"))


def _slugify(name: str) -> str:
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", name.lower()))


@router.post("/events/{event_id}/sync-wom")
async def sync_event_from_wom(
    event_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> dict[str, Any]:
    """Pull teams, participants, and dates from the linked WOM competition."""
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    if not event.wom_comp_id:
        raise HTTPException(400, "Event has no WOM competition ID set.")

    async with WiseOldManHandler(
        api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT, timeout=15.0
    ) as wom:
        comp = await wom.get_competition_details(event.wom_comp_id)

    now = datetime.now(UTC)
    if comp.get("startsAt"):
        event.starts_at = datetime.fromisoformat(
            comp["startsAt"].replace("Z", "+00:00")
        )
    if comp.get("endsAt"):
        event.ends_at = datetime.fromisoformat(comp["endsAt"].replace("Z", "+00:00"))
    event.updated_at = now

    synced_teams: list[dict[str, Any]] = []
    if comp.get("type") == "team":
        teams_map: dict[str, list[str]] = {}
        for p in comp.get("participations", []):
            t_name = p.get("teamName", "")
            rsn = (p.get("player") or {}).get("displayName", "")
            if t_name and rsn:
                teams_map.setdefault(t_name, []).append(rsn)

        existing = {
            t.slug: t
            for t in (
                await session.execute(
                    select(FrenzyTeam).where(FrenzyTeam.event_id == event_id)
                )
            )
            .scalars()
            .all()
        }

        for i, (team_name, participants) in enumerate(teams_map.items()):
            slug = _slugify(team_name)
            if slug in existing:
                existing[slug].participants = participants
                existing[slug].updated_at = now
            else:
                session.add(
                    FrenzyTeam(
                        event_id=event_id,
                        name=team_name,
                        slug=slug,
                        icon_url=None,
                        sort_order=i,
                        participants=participants,
                        item_progress={},
                        activity_progress={},
                        milestone_progress={},
                        updated_at=now,
                    )
                )
            synced_teams.append(
                {"name": team_name, "slug": slug, "participants": participants}
            )

    await session.commit()
    return {
        "starts_at": event.starts_at.isoformat() if event.starts_at else None,
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "teams_synced": len(synced_teams),
        "teams": synced_teams,
    }
