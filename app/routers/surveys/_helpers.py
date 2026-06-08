from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SurveyActive, SurveyResponse, SurveyTemplate, WebSurveySubmission
from app.services.page_permissions import check_page_permission
from app.services.rank_mappings import get_effective_roles


def normalize_visibility(raw: str | list | None) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return [raw]
    return raw


async def get_roles(current_user: dict, session: AsyncSession) -> list[str]:
    discord_user_id = int(current_user["sub"])
    return await get_effective_roles(discord_user_id, session)


def extract_fields(raw: list | dict) -> list[dict]:
    fields: list[dict] = raw if isinstance(raw, list) else raw.get("fields", [])
    return [{**f, "label": f["text"]} if "label" not in f and "text" in f else f for f in fields]


def extract_is_open(raw: list | dict) -> bool:
    if isinstance(raw, list):
        return False
    if "is_open" in raw:
        return bool(raw["is_open"])
    return raw.get("visibility") is not None


async def list_templates(
    category: str, roles: list[str], discord_user_id: int, session: AsyncSession
) -> list[dict]:
    is_staff = await check_page_permission("staff.surveys", "read", roles, session)

    active_row = (await session.execute(select(SurveyActive))).scalar_one_or_none()
    active_template_id = active_row.template_id if active_row else None

    response_counts: dict[str, int] = {
        r[0]: r[1]
        for r in await session.execute(
            select(SurveyResponse.template_id, func.count().label("count")).group_by(SurveyResponse.template_id)
        )
    }
    web_response_counts: dict[str, int] = {
        r[0]: r[1]
        for r in await session.execute(
            select(WebSurveySubmission.template_id, func.count().label("count")).group_by(WebSurveySubmission.template_id)
        )
    }
    submitted_set: set[str] = {
        r.template_id
        for r in await session.execute(
            select(WebSurveySubmission.template_id).where(WebSurveySubmission.discord_user_id == discord_user_id)
        )
    }

    rows = (await session.execute(select(SurveyTemplate))).scalars().all()
    out: list[dict] = []
    for row in rows:
        raw = row.questions or {}
        if isinstance(raw, list):
            row_category, visibility, description = "survey", None, None
        else:
            row_category = raw.get("category", "survey")
            visibility = normalize_visibility(raw.get("visibility"))
            description = raw.get("description")

        if row_category != category:
            continue

        is_open = extract_is_open(raw)
        if not is_staff:
            if not is_open and row.template_id not in submitted_set:
                continue

        entry: dict = {
            "template_id": row.template_id,
            "title": row.title,
            "description": description,
            "is_open": is_open,
            "visibility": visibility,
            "category": row_category,
            "is_active": row.template_id == active_template_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "user_submitted": row.template_id in submitted_set,
        }
        if is_staff:
            entry["response_count"] = response_counts.get(row.template_id, 0)
            entry["web_response_count"] = web_response_counts.get(row.template_id, 0)
        out.append(entry)

    return out
