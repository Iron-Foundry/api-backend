from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.page_permissions import check_page_permission, get_admin_bypass_roles
from app.services.rank_mappings import get_effective_roles, get_role_label_map

_DISCORD_ROLE_ORDER = [
    "Guest", "Achiever", "Sapphire", "Emerald", "Ruby", "Diamond",
    "Dragonstone", "Onyx", "Zenyte", "Ex-Moderator", "Foundry Mentors",
    "Event Team", "Moderator", "Senior Moderator", "Deputy Owner", "Co-owner",
]

_TICKET_TYPE_MIN_RANK: dict[str, str] = {
    "contact_mentor": "Foundry Mentors",
    "general": "Moderator",
    "rankup": "Moderator",
    "join_cc": "Moderator",
    "apply_staff": "Senior Moderator",
    "apply_mentor": "Senior Moderator",
    "apply_event_team": "Senior Moderator",
    "sensitive": "Senior Moderator",
    "survey": "Senior Moderator",
}

_SOURCE_LABELS: dict[str | None, str] = {
    "reddit": "Reddit",
    "osrs_discord": "OSRS Discord",
    "website": "Website",
    "recruited_by": "Recruited by",
    "instagram": "Instagram",
    "other": "Other",
    None: "Unanswered",
}


def has_min_rank_by_label(role_labels: list[str], min_role: str) -> bool:
    try:
        min_idx = _DISCORD_ROLE_ORDER.index(min_role)
    except ValueError:
        return False
    for label in role_labels:
        if label in _DISCORD_ROLE_ORDER and _DISCORD_ROLE_ORDER.index(label) >= min_idx:
            return True
    return False


def allowed_ticket_types(role_labels: list[str]) -> list[str]:
    return [t for t, min_r in _TICKET_TYPE_MIN_RANK.items() if has_min_rank_by_label(role_labels, min_r)]


async def get_roles(current_user: dict, session: AsyncSession) -> list[str]:
    discord_user_id = int(current_user["sub"])
    return await get_effective_roles(discord_user_id, session)


async def require_rank(page_id: str, action: str, current_user: dict, session: AsyncSession) -> None:
    roles = await get_roles(current_user, session)
    if not await check_page_permission(page_id, action, roles, session):
        raise HTTPException(status_code=403, detail="Permission denied.")


async def get_allowed_ticket_types(roles: list[str], session: AsyncSession) -> list[str]:
    bypass_roles = await get_admin_bypass_roles(session)
    if any(r in bypass_roles for r in roles):
        return list(_TICKET_TYPE_MIN_RANK.keys())
    id_to_label = await get_role_label_map(session)
    role_labels = [id_to_label.get(r, r) for r in roles]
    return allowed_ticket_types(role_labels)
