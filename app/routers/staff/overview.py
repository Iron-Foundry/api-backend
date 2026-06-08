from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Ticket, User
from app.dependencies import get_current_user, get_session

from ._helpers import _SOURCE_LABELS, require_rank

router = APIRouter()


@router.get("/referral-stats")
async def referral_stats(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Referral source breakdown + recruiter leaderboard."""
    await require_rank("staff.home", "read", current_user, session)

    source_rows = await session.execute(
        select(User.referral_source, func.count().label("count")).group_by(User.referral_source)
    )
    sources = [
        {
            "source": row.referral_source,
            "label": _SOURCE_LABELS.get(row.referral_source, row.referral_source or "Unanswered"),
            "count": row.count,
        }
        for row in source_rows
    ]

    recruiter_rows = await session.execute(
        select(User.referral_detail, func.count().label("count"))
        .where(User.referral_source == "recruited_by")
        .group_by(User.referral_detail)
        .order_by(func.count().desc())
    )
    recruiters = [{"name": row.referral_detail or "Unknown", "count": row.count} for row in recruiter_rows]

    return {"sources": sources, "recruiters": recruiters}


@router.get("/overview")
async def staff_overview(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """High-level clan stats. Requires Mentor or higher."""
    await require_rank("staff.home", "read", current_user, session)

    total_members = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    open_tickets = (
        await session.execute(select(func.count()).select_from(Ticket).where(Ticket.status == "open"))
    ).scalar_one()
    total_tickets = (await session.execute(select(func.count()).select_from(Ticket))).scalar_one()

    return {
        "total_members": total_members,
        "open_tickets": open_tickets,
        "total_tickets": total_tickets,
    }
