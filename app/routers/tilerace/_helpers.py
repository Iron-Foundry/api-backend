from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PlayerSnapshot, TileRaceSignup, TileRepositoryTile

from ._draft import raids_kc
from ._serializers import _serialize_tile


async def _embed_cells(
    cells: list[dict[str, Any]], session: AsyncSession
) -> list[dict[str, Any]]:
    tile_ids = {int(c["tile_id"]) for c in cells if c.get("tile_id")}
    tiles: dict[int, dict[str, Any]] = {}
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


async def raids_kc_map(
    session: AsyncSession, signups: list[TileRaceSignup]
) -> dict[str, int]:
    """Highest single-raid KC per RSN, for every member on the roster."""
    names = {s.rsn.lower() for s in signups if s.rsn}
    if not names:
        return {}
    rows = (
        (
            await session.execute(
                select(PlayerSnapshot).where(PlayerSnapshot.rsn.in_(names))
            )
        )
        .scalars()
        .all()
    )
    return {r.rsn.lower(): raids_kc(r.bosses) for r in rows}


def group_by_team(
    signups: list[TileRaceSignup],
) -> dict[int, list[TileRaceSignup]]:
    grouped: dict[int, list[TileRaceSignup]] = {}
    for signup in signups:
        if signup.team_id is not None:
            grouped.setdefault(signup.team_id, []).append(signup)
    return grouped
