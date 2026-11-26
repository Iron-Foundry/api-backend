from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzySubmission, FrenzyTeam

PlayerValues = dict[str, dict[int, int]]


def _item_key(payload: dict[str, Any]) -> str:
    return f"{payload['tier']}.{payload['source_name']}.{payload['item_name']}"


def _keep_player_best(
    by_player: PlayerValues, sub: FrenzySubmission, payload: dict[str, Any]
) -> None:
    name = payload["name"]
    uid = sub.discord_user_id
    by_player.setdefault(name, {})
    by_player[name][uid] = max(by_player[name].get(uid, 0), payload.get("value", 0))


def _fold_submissions(
    subs: Sequence[FrenzySubmission], item_p: dict[str, Any]
) -> tuple[PlayerValues, PlayerValues]:
    act_by_player: PlayerValues = {}
    mil_by_player: PlayerValues = {}
    for sub in subs:
        p = sub.payload or {}
        if sub.submission_type == "item":
            key = _item_key(p)
            item_p[key] = item_p.get(key, 0) + p.get("quantity", 1)
        elif sub.submission_type == "activity":
            _keep_player_best(act_by_player, sub, p)
        elif sub.submission_type == "milestone":
            _keep_player_best(mil_by_player, sub, p)
    return act_by_player, mil_by_player


def _apply_pending_submissions(
    base_item: dict[str, Any],
    base_activity: dict[str, Any],
    base_milestone: dict[str, Any],
    pending: Sequence[FrenzySubmission],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    item_p = dict(base_item)
    act_by_player, mil_by_player = _fold_submissions(pending, item_p)

    act_p = dict(base_activity)
    for name, by_player in act_by_player.items():
        act_p[name] = act_p.get(name, 0) + sum(by_player.values())

    mil_p = dict(base_milestone)
    for name, by_player in mil_by_player.items():
        mil_p[name] = mil_p.get(name, 0) + sum(by_player.values())

    return item_p, act_p, mil_p


async def _recompute_team_progress(session: AsyncSession, team: FrenzyTeam) -> None:
    """Rebuild team JSONB caches from all approved submissions for this team."""
    submissions = (
        (
            await session.execute(
                select(FrenzySubmission)
                .where(
                    FrenzySubmission.team_id == team.id,
                    FrenzySubmission.status == "approved",
                )
                .order_by(FrenzySubmission.submitted_at)
            )
        )
        .scalars()
        .all()
    )

    item_progress: dict[str, Any] = {}
    activity_by_player, milestone_by_player = _fold_submissions(
        submissions, item_progress
    )

    team.item_progress = item_progress
    team.activity_progress = {n: sum(v.values()) for n, v in activity_by_player.items()}
    team.milestone_progress = {
        n: sum(v.values()) for n, v in milestone_by_player.items()
    }
    team.updated_at = datetime.now(UTC)
