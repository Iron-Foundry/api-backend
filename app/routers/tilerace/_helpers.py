from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    TileRepositoryTile,
    TileRaceCompletion,
    TileRaceEvent,
    TileRaceRoll,
    TileRaceSignup,
    TileRaceTeam,
)

from .requirement_schema import requirement_from_items


def _serialize_tile(t: TileRepositoryTile) -> dict:
    items = t.items or []
    return {
        "id": str(t.id),
        "title": t.title,
        "description": t.description,
        "icon_url": t.icon_url,
        "icon_source": t.icon_source,
        "items": items,
        "requirement": t.requirement or requirement_from_items(items),
        "tags": t.tags or [],
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }


async def _embed_cells(cells: list, session: AsyncSession) -> list[dict]:
    tile_ids = {int(c["tile_id"]) for c in cells if c.get("tile_id")}
    tiles: dict[int, dict] = {}
    if tile_ids:
        rows = (
            (
                await session.execute(
                    select(TileRepositoryTile).where(
                        TileRepositoryTile.id.in_(tile_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        for t in rows:
            tiles[t.id] = _serialize_tile(t)
    result = []
    for cell in cells:
        c = dict(cell)
        tid = c.get("tile_id")
        if tid and int(tid) in tiles:
            c["tile"] = tiles[int(tid)]
        result.append(c)
    return result


def _serialize_summary(e: TileRaceEvent) -> dict:
    return {
        "id": str(e.id),
        "name": e.name,
        "is_active": e.is_active,
        "signups_open": e.signups_open,
        "fog_of_war": e.fog_of_war,
        "grid_cols": e.grid_cols,
        "grid_rows": e.grid_rows,
        "dice_count": e.dice_count,
        "dice_sides": e.dice_sides,
        "start_pad": e.start_pad,
        "end_pad": e.end_pad,
        "is_finished": e.is_finished,
        "winner_team_id": str(e.winner_team_id) if e.winner_team_id else None,
        "background_url": e.background_url,
        "starts_at": e.starts_at.isoformat() if e.starts_at else None,
        "ends_at": e.ends_at.isoformat() if e.ends_at else None,
        "created_at": e.created_at.isoformat(),
    }


def _serialize_team(t: TileRaceTeam) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "slug": t.slug,
        "icon_type": t.icon_type,
        "icon_url": t.icon_url,
        "color": t.color,
        "position": t.position,
        "members": t.members or [],
        "pending_effects": t.pending_effects or {},
    }


def _serialize_signup(s: TileRaceSignup) -> dict:
    return {
        "discord_user_id": str(s.discord_user_id),
        "account_id": s.account_id,
        "rsn": s.rsn,
        "ranking_score": s.ranking_score,
        "wants_captain": s.wants_captain,
        "signed_up_at": s.signed_up_at.isoformat(),
    }


def _serialize_roll(r: TileRaceRoll) -> dict:
    return {
        "id": str(r.id),
        "team_id": str(r.team_id),
        "dice": r.dice or [],
        "roll": r.roll,
        "skipped": r.skipped,
        "new_position": r.new_position,
        "rolled_by": str(r.rolled_by),
        "rolled_at": r.rolled_at.isoformat(),
    }


def _serialize_completion(c: TileRaceCompletion) -> dict:
    return {
        "team_id": str(c.team_id),
        "path_position": c.path_position,
        "completed_by": str(c.completed_by) if c.completed_by else None,
        "completed_at": c.completed_at.isoformat(),
    }
