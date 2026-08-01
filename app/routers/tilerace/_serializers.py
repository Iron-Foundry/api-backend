from __future__ import annotations

from typing import Any

from app.db.models import (
    TileRaceCompletion,
    TileRaceEvent,
    TileRaceRoll,
    TileRaceSignup,
    TileRaceTeam,
    TileRepositoryTile,
)

from ._discord_perms import normalize as normalize_perms
from .requirement_schema import requirement_from_items


def _id_or_none(value: int | None) -> str | None:
    return str(value) if value is not None else None


def _serialize_tile(t: TileRepositoryTile) -> dict[str, Any]:
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


def _serialize_summary(e: TileRaceEvent) -> dict[str, Any]:
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
        "team_size": e.team_size,
        "start_pad": e.start_pad,
        "end_pad": e.end_pad,
        "is_finished": e.is_finished,
        "rolls_paused": e.rolls_paused,
        "winner_team_id": str(e.winner_team_id) if e.winner_team_id else None,
        "discord_provisioned": e.discord_category_id is not None,
        "discord_category_id": _id_or_none(e.discord_category_id),
        "discord_captains_role_id": _id_or_none(e.discord_captains_role_id),
        "discord_captains_channel_id": _id_or_none(e.discord_captains_channel_id),
        "discord_permissions": normalize_perms(e.discord_permissions),
        "background_url": e.background_url,
        "starts_at": e.starts_at.isoformat() if e.starts_at else None,
        "ends_at": e.ends_at.isoformat() if e.ends_at else None,
        "created_at": e.created_at.isoformat(),
    }


def _kc(s: TileRaceSignup, kc_map: dict[str, int]) -> int:
    return kc_map.get(s.rsn.lower(), 0) if s.rsn else 0


def _serialize_member(s: TileRaceSignup, kc_map: dict[str, int]) -> dict[str, Any]:
    return {
        "discord_user_id": str(s.discord_user_id),
        "rsn": s.rsn,
        "ranking_score": s.ranking_score,
        "raids_kc": _kc(s, kc_map),
        "is_captain": s.is_captain,
    }


def _serialize_team(
    t: TileRaceTeam,
    members: list[TileRaceSignup] | None = None,
    kc_map: dict[str, int] | None = None,
) -> dict[str, Any]:
    roster = sorted(
        members or [], key=lambda s: (not s.is_captain, -s.ranking_score, s.rsn.lower())
    )
    kc_map = kc_map or {}
    return {
        "id": str(t.id),
        "name": t.name,
        "slug": t.slug,
        "icon_type": t.icon_type,
        "icon_url": t.icon_url,
        "color": t.color,
        "position": t.position,
        "discord_role_id": _id_or_none(t.discord_role_id),
        "discord_text_channel_id": _id_or_none(t.discord_text_channel_id),
        "discord_voice_channel_id": _id_or_none(t.discord_voice_channel_id),
        "members": [_serialize_member(s, kc_map) for s in roster],
        "pending_effects": t.pending_effects or {},
    }


def _serialize_signup(
    s: TileRaceSignup, kc_map: dict[str, int] | None = None
) -> dict[str, Any]:
    return {
        "discord_user_id": str(s.discord_user_id),
        "team_id": str(s.team_id) if s.team_id else None,
        "account_id": s.account_id,
        "rsn": s.rsn,
        "ranking_score": s.ranking_score,
        "raids_kc": _kc(s, kc_map or {}),
        "wants_captain": s.wants_captain,
        "is_captain": s.is_captain,
        "added_by_staff": s.added_by_staff,
        "signed_up_at": s.signed_up_at.isoformat(),
    }


def _serialize_roll(r: TileRaceRoll) -> dict[str, Any]:
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


def _serialize_completion(c: TileRaceCompletion) -> dict[str, Any]:
    return {
        "team_id": str(c.team_id),
        "path_position": c.path_position,
        "completed_by": str(c.completed_by) if c.completed_by else None,
        "completed_at": c.completed_at.isoformat(),
    }
