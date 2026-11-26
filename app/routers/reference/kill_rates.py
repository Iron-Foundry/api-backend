from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SourceKillRate, User
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import require_page_permission

from ._schemas import KillRateBody, KillRateOut, KillRatePage

router = APIRouter(prefix="/kill-rates")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SourcePath = Annotated[str, Path(min_length=1, max_length=200)]
_PERM = Depends(require_page_permission("frenzy.admin", "edit"))


def _named_rates() -> Select[tuple[SourceKillRate, str]]:
    return select(SourceKillRate, User.discord_username).outerjoin(
        User, User.discord_user_id == SourceKillRate.set_by
    )


def _rate_out(row: SourceKillRate, set_by_name: str | None) -> KillRateOut:
    return KillRateOut(
        source=row.source,
        kills_per_hour=row.kills_per_hour,
        set_by=row.set_by,
        set_by_name=set_by_name,
        updated_at=row.updated_at,
    )


async def _named_rate(session: AsyncSession, source: str) -> KillRateOut:
    stmt = _named_rates().where(SourceKillRate.source == source)
    found = (await session.execute(stmt)).one_or_none()
    if found is None:
        raise HTTPException(status_code=404, detail="Kill rate not found")
    return _rate_out(*found)


@router.get("")
async def list_kill_rates(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> KillRatePage:
    """List the staff-set kill rates of OSRSClans drop sources, by source key."""
    count = select(func.count(SourceKillRate.source))
    total = (await session.execute(count)).scalar_one()
    stmt = _named_rates().order_by(SourceKillRate.source).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).all()
    items = [_rate_out(row, name) for row, name in rows]
    return KillRatePage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{source}")
async def get_kill_rate(source: SourcePath, session: SessionDep) -> KillRateOut:
    """Return the staff-set kill rate of one OSRSClans drop source, URL-encoded."""
    return await _named_rate(session, source)


@router.put("/{source}")
async def set_kill_rate(
    source: SourcePath,
    body: KillRateBody,
    session: SessionDep,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    _perm: None = _PERM,
) -> KillRateOut:
    """Set the kill rate of an OSRSClans drop source that has none of its own.

    `source` is the OSRSClans source key, URL-encoded. A source that OSRSClans
    gives a rate keeps that rate on the loot rate routes.
    """
    values = {
        "kills_per_hour": body.kills_per_hour,
        "set_by": int(current_user["sub"]),
        "updated_at": datetime.now(UTC),
    }
    stmt = (
        insert(SourceKillRate)
        .values(source=source, **values)
        .on_conflict_do_update(index_elements=[SourceKillRate.source], set_=values)
    )
    await session.execute(stmt)
    await session.commit()
    return await _named_rate(session, source)


@router.delete("/{source}", status_code=204)
async def remove_kill_rate(
    source: SourcePath, session: SessionDep, _perm: None = _PERM
) -> None:
    """Remove the staff-set kill rate of an OSRSClans drop source."""
    row = await session.get(SourceKillRate, source)
    if row is None:
        raise HTTPException(status_code=404, detail="Kill rate not found")
    await session.delete(row)
    await session.commit()
