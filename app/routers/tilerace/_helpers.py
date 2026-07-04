from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    TileRepositoryTile,
    TileRaceEvent,
    TileRaceSignup,
    TileRaceTeam,
)


def _serialize_tile(t: TileRepositoryTile) -> dict:
    return {
        "id": str(t.id),
        "title": t.title,
        "description": t.description,
        "icon_url": t.icon_url,
        "icon_source": t.icon_source,
        "items": t.items or [],
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
        "fog_of_war": e.fog_of_war,
        "grid_cols": e.grid_cols,
        "grid_rows": e.grid_rows,
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
    }


def _serialize_signup(s: TileRaceSignup) -> dict:
    return {
        "discord_user_id": str(s.discord_user_id),
        "rsn": s.rsn,
        "ranking_score": s.ranking_score,
        "signed_up_at": s.signed_up_at.isoformat(),
    }
