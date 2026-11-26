"""Loading a frenzy draft and its signups, and building the public draft view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyDraft, FrenzySignup, FrenzyTeam, PlayerRanking

from ._snake import snake_slot
from .draft_schemas import (
    DraftMember,
    DraftMode,
    DraftState,
    DraftTeam,
    DraftView,
    PickKind,
)


@dataclass(frozen=True)
class Ranking:
    rank: str
    points: int


async def draft_or_404(session: AsyncSession, event_id: int) -> FrenzyDraft:
    draft = (
        await session.execute(
            select(FrenzyDraft).where(FrenzyDraft.event_id == event_id)
        )
    ).scalar_one_or_none()
    if draft is None:
        raise HTTPException(404, "This event has no draft.")
    return draft


async def event_signups(session: AsyncSession, event_id: int) -> list[FrenzySignup]:
    rows = await session.execute(
        select(FrenzySignup)
        .where(FrenzySignup.event_id == event_id)
        .order_by(FrenzySignup.signed_up_at, FrenzySignup.id)
    )
    return list(rows.scalars().all())


async def rankings(session: AsyncSession, rsns: list[str]) -> dict[str, Ranking]:
    """The clan ranking of each RSN, keyed by the lowercased RSN, in one query."""
    lowered = {rsn.lower() for rsn in rsns}
    if not lowered:
        return {}
    key = func.lower(PlayerRanking.rsn)
    rows = await session.execute(
        select(key, PlayerRanking.rank, PlayerRanking.points).where(key.in_(lowered))
    )
    found: dict[str, Ranking] = {}
    for rsn, rank, points in rows.all():
        if rsn not in found or points > found[rsn].points:
            found[rsn] = Ranking(rank, points)
    return found


def strongest_first(
    signups: list[FrenzySignup], ranked: dict[str, Ranking]
) -> list[FrenzySignup]:
    """Highest ranking points first; ties go to the earlier signup."""

    def points(s: FrenzySignup) -> int:
        found = ranked.get(s.rsn.lower())
        return found.points if found else 0

    return sorted(signups, key=lambda s: (-points(s), s.signed_up_at, s.id))


def member(signup: FrenzySignup, ranked: dict[str, Ranking]) -> DraftMember:
    found = ranked.get(signup.rsn.lower())
    return DraftMember(
        signup_id=signup.id,
        rsn=signup.rsn,
        timezone=signup.timezone,
        rank=found.rank if found else None,
        points=found.points if found else None,
        wants_captain=signup.wants_captain,
        pick_number=signup.pick_number,
        pick_kind=cast(PickKind | None, signup.pick_kind),
    )


async def build_view(session: AsyncSession, draft: FrenzyDraft) -> DraftView:
    signups = await event_signups(session, draft.event_id)
    ranked = await rankings(session, [s.rsn for s in signups])
    by_id = {s.id: s for s in signups}
    names = {
        t.id: t.name
        for t in (
            await session.execute(
                select(FrenzyTeam).where(FrenzyTeam.event_id == draft.event_id)
            )
        ).scalars()
    }
    teams = []
    for team_id, captain_id in zip(draft.team_ids, draft.captain_ids, strict=False):
        captain = by_id[captain_id]
        roster = sorted(
            (s for s in signups if s.team_id == team_id and s.id != captain_id),
            key=lambda s: s.pick_number or 0,
        )
        teams.append(
            DraftTeam(
                team_id=team_id,
                name=names.get(team_id, captain.rsn),
                captain=member(captain, ranked),
                captain_discord_user_id=str(captain.discord_user_id),
                members=[member(s, ranked) for s in roster],
            )
        )
    captain_set = set(draft.captain_ids)
    pool = [s for s in signups if s.team_id is None and s.id not in captain_set]
    picking = None
    if draft.state == "picking" and draft.team_ids:
        picking = draft.team_ids[snake_slot(draft.next_pick, len(draft.team_ids))]
    return DraftView(
        event_id=draft.event_id,
        mode=cast(DraftMode, draft.mode),
        top_picks=draft.top_picks,
        state=cast(DraftState, draft.state),
        next_pick=draft.next_pick,
        picking_team_id=picking,
        captains=[member(by_id[c], ranked) for c in draft.captain_ids if c in by_id],
        teams=teams,
        pool=[member(s, ranked) for s in strongest_first(pool, ranked)],
    )
