from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyEvent, FrenzyTeam, FrenzyTemplate
from app.dependencies import get_current_user, get_session
from app.services.http import WiseOldManHandler
from app.services.page_permissions import require_page_permission

from ._constants import _WOM_API_KEY, _WOM_DISCORD_CONTACT
from .schemas import EventBody, EventPatch

router = APIRouter()

_PERM = Depends(require_page_permission("frenzy", "edit"))


def _slugify(name: str) -> str:
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", name.lower()))


@router.get("/events")
async def list_events(
    session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> list[dict]:
    rows = (
        (
            await session.execute(
                select(FrenzyEvent).order_by(FrenzyEvent.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": e.id,
            "name": e.name,
            "template_id": e.template_id,
            "wom_comp_id": e.wom_comp_id,
            "starts_at": e.starts_at.isoformat() if e.starts_at else None,
            "ends_at": e.ends_at.isoformat() if e.ends_at else None,
            "is_active": e.is_active,
            "created_at": e.created_at.isoformat(),
        }
        for e in rows
    ]


@router.post("/events", status_code=201)
async def create_event(
    body: EventBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
    current_user: dict = Depends(get_current_user),
) -> dict:
    tmpl = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == body.template_id)
        )
    ).scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(404, "Template not found.")

    now = datetime.now(timezone.utc)
    event = FrenzyEvent(
        name=body.name,
        template_id=body.template_id,
        wom_comp_id=body.wom_comp_id,
        leaderboard_metrics=body.leaderboard_metrics,
        trusted_sources=body.trusted_sources,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        is_active=False,
        created_by=int(current_user["sub"]),
        created_at=now,
        updated_at=now,
    )
    session.add(event)
    await session.commit()
    return {"id": event.id}


@router.get("/events/{event_id}")
async def get_event(
    event_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> dict:
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")

    teams = (
        (
            await session.execute(
                select(FrenzyTeam)
                .where(FrenzyTeam.event_id == event_id)
                .order_by(FrenzyTeam.sort_order)
            )
        )
        .scalars()
        .all()
    )

    return {
        "id": event.id,
        "name": event.name,
        "template_id": event.template_id,
        "wom_comp_id": event.wom_comp_id,
        "leaderboard_metrics": event.leaderboard_metrics,
        "trusted_sources": event.trusted_sources or [],
        "starts_at": event.starts_at.isoformat() if event.starts_at else None,
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "is_active": event.is_active,
        "created_at": event.created_at.isoformat(),
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "icon_url": t.icon_url,
                "sort_order": t.sort_order,
                "participants": t.participants or [],
            }
            for t in teams
        ],
    }


@router.patch("/events/{event_id}")
async def patch_event(
    event_id: int,
    body: EventPatch,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict:
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")

    if body.name is not None:
        event.name = body.name
    if body.wom_comp_id is not None:
        event.wom_comp_id = body.wom_comp_id
    if body.leaderboard_metrics is not None:
        event.leaderboard_metrics = body.leaderboard_metrics
    if body.trusted_sources is not None:
        event.trusted_sources = body.trusted_sources
    if body.starts_at is not None:
        event.starts_at = body.starts_at
    if body.ends_at is not None:
        event.ends_at = body.ends_at
    event.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return {"ok": True}


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> dict:
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    await session.delete(event)
    await session.commit()
    return {"ok": True}


@router.post("/events/{event_id}/activate")
async def activate_event(
    event_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> dict:
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    await session.execute(
        update(FrenzyEvent).where(FrenzyEvent.id != event_id).values(is_active=False)
    )
    event.is_active = True
    await session.commit()
    return {"ok": True, "active_event_id": event_id}


@router.post("/events/{event_id}/deactivate")
async def deactivate_event(
    event_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> dict:
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    event.is_active = False
    await session.commit()
    return {"ok": True}


@router.post("/events/{event_id}/sync-wom")
async def sync_event_from_wom(
    event_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> dict:
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

    now = datetime.now(timezone.utc)
    if comp.get("startsAt"):
        event.starts_at = datetime.fromisoformat(
            comp["startsAt"].replace("Z", "+00:00")
        )
    if comp.get("endsAt"):
        event.ends_at = datetime.fromisoformat(comp["endsAt"].replace("Z", "+00:00"))
    event.updated_at = now

    synced_teams: list[dict] = []
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
