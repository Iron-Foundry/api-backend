"""Resolve competition participants and grant placement and bonus tokens."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.users import User, UserAccount

from .ballot_tokens import award_tokens


def _gained(participation: dict) -> int:
    return (participation.get("progress") or {}).get("gained", 0) or 0


async def resolve_rsns(session: AsyncSession, names: list[str]) -> dict[str, int]:
    """Map lowercased RSNs to discord_user_id via user_accounts then users.rsn."""
    lowered = [n.lower() for n in names if n]
    if not lowered:
        return {}
    resolved: dict[str, int] = {}
    account_rows = await session.execute(
        select(func.lower(UserAccount.rsn), UserAccount.discord_user_id).where(
            func.lower(UserAccount.rsn).in_(lowered)
        )
    )
    for rsn, uid in account_rows.all():
        resolved[rsn] = uid
    missing = [n for n in lowered if n not in resolved]
    if missing:
        user_rows = await session.execute(
            select(func.lower(User.rsn), User.discord_user_id).where(
                func.lower(User.rsn).in_(missing)
            )
        )
        for rsn, uid in user_rows.all():
            if rsn is not None:
                resolved[rsn] = uid
    return resolved


def compute_award_plan(
    ranked: list[dict], resolved: dict[str, int], config: dict
) -> list[tuple[int, int, str]]:
    """Build (discord_user_id, amount, reason) awards from ranked participations."""
    if not ranked or _gained(ranked[0]) <= 0:
        return []

    placement_tokens: list[int] = config["placement_tokens"]
    bonus_tokens: int = config["bonus_tokens"]
    threshold = _gained(ranked[0]) * config["bonus_threshold_pct"] / 100

    awards: list[tuple[int, int, str]] = []
    for index, participation in enumerate(ranked):
        rsn = participation.get("player", {}).get("displayName", "").lower()
        uid = resolved.get(rsn)
        if uid is None:
            continue
        if index < len(placement_tokens) and placement_tokens[index] > 0:
            awards.append((uid, placement_tokens[index], "placement_award"))
        if _gained(participation) >= threshold and bonus_tokens > 0:
            awards.append((uid, bonus_tokens, "bonus_award"))
    return awards


async def process_run_awards(
    session: AsyncSession,
    run_id: int,
    participations: list[dict],
    config: dict,
) -> dict:
    """Grant placement (1st-5th) and >=threshold%-of-rank-1 bonus tokens."""
    ranked = sorted(participations, key=_gained, reverse=True)
    names = [p.get("player", {}).get("displayName", "") for p in ranked]
    resolved = await resolve_rsns(session, names)
    awards = compute_award_plan(ranked, resolved, config)

    await award_tokens(session, awards, run_id, config["max_hold"])
    recipients = len({uid for uid, _, _ in awards})
    total = sum(amount for _, amount, _ in awards)
    return {"recipients": recipients, "total": total}
