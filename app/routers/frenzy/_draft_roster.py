"""Writing draft results onto signups and teams: picks, the hand-out, participants."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyDraft, FrenzySignup, FrenzyTeam

from ._draft_view import event_signups, rankings, strongest_first
from ._snake import hand_out, manual_picks_left


def team_slug(rsn: str, taken: set[str]) -> str:
    """A slug from the captain's RSN that no other team of the event uses."""
    base = re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", rsn.lower())) or "team"
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    return slug


async def create_captain_teams(
    session: AsyncSession, event_id: int, captains: list[FrenzySignup]
) -> list[int]:
    """One team per captain, in drawn order, each named for its captain."""
    now = datetime.now(UTC)
    taken: set[str] = set()
    teams = []
    for position, captain in enumerate(captains):
        slug = team_slug(captain.rsn, taken)
        taken.add(slug)
        team = FrenzyTeam(
            event_id=event_id,
            name=captain.rsn,
            slug=slug,
            sort_order=position,
            participants=[captain.rsn],
            item_progress={},
            activity_progress={},
            milestone_progress={},
            updated_at=now,
        )
        session.add(team)
        teams.append(team)
    await session.flush()
    for team, captain in zip(teams, captains, strict=True):
        captain.team_id = team.id
        captain.pick_kind = "captain"
    return [team.id for team in teams]


async def sync_participants(session: AsyncSession, event_id: int) -> None:
    """Set each team's participants to its signups' RSNs, captain first."""
    signups = await event_signups(session, event_id)
    teams = (
        await session.execute(select(FrenzyTeam).where(FrenzyTeam.event_id == event_id))
    ).scalars()
    now = datetime.now(UTC)
    for team in teams:
        roster = sorted(
            (s for s in signups if s.team_id == team.id),
            key=lambda s: (s.pick_kind != "captain", s.pick_number or 0),
        )
        team.participants = [s.rsn for s in roster]
        team.updated_at = now


def pool_of(draft: FrenzyDraft, signups: list[FrenzySignup]) -> list[FrenzySignup]:
    captains = set(draft.captain_ids)
    return [s for s in signups if s.team_id is None and s.id not in captains]


async def finish_if_done(session: AsyncSession, draft: FrenzyDraft) -> None:
    """Hand out the rest once no manual pick is left, then mark the draft complete."""
    signups = await event_signups(session, draft.event_id)
    pool = pool_of(draft, signups)
    if manual_picks_left(
        draft.mode, draft.top_picks, draft.next_pick, len(draft.team_ids), len(pool)
    ):
        return
    ranked = await rankings(session, [s.rsn for s in pool])
    ordered = [s.id for s in strongest_first(pool, ranked)]
    by_id = {s.id: s for s in pool}
    for signup_id, team_id, pick in hand_out(draft.team_ids, draft.next_pick, ordered):
        signup = by_id[signup_id]
        signup.team_id = team_id
        signup.pick_number = pick
        signup.pick_kind = "auto"
    draft.next_pick += len(ordered)
    draft.state = "complete"


def clear_assignment(signup: FrenzySignup) -> None:
    signup.team_id = None
    signup.pick_number = None
    signup.pick_kind = None
