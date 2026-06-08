from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal
import os

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Asset, FeedbackReply, User

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/avif"}
_ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_VALID_TYPES = ("suggestion", "bug")
_VALID_STATUSES = ("open", "in-review", "implemented", "wont-fix", "solved", "closed")


class SubmitFeedbackBody(BaseModel):
    type: Literal["suggestion", "bug"]
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=4000)
    is_anonymous: bool = False
    steps_to_reproduce: str | None = Field(None, max_length=4000)
    attachment_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_steps_for_bugs(self) -> "SubmitFeedbackBody":
        if self.type == "bug" and not self.steps_to_reproduce:
            raise ValueError("steps_to_reproduce is required for bug reports")
        return self


class EditFeedbackBody(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1, max_length=4000)
    steps_to_reproduce: str | None = Field(None, max_length=4000)
    is_anonymous: bool | None = None
    attachment_ids: list[str] | None = None


class UpdateStatusBody(BaseModel):
    status: Literal["open", "planned", "implemented", "needs-triage", "wont-add", "reviewing", "patched", "wont-fix"]


class PostReplyBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


async def get_username(discord_user_id: int, session: AsyncSession) -> str | None:
    from sqlalchemy import select
    result = await session.execute(
        select(User.discord_username).where(User.discord_user_id == discord_user_id)
    )
    return result.scalar_one_or_none()


async def get_user_info(discord_user_id: int, session: AsyncSession) -> tuple[str | None, str | None]:
    from sqlalchemy import select
    result = await session.execute(
        select(User.discord_username, User.clan_rank).where(User.discord_user_id == discord_user_id)
    )
    row = result.one_or_none()
    if row:
        return row.discord_username, row.clan_rank
    return None, None


async def resolve_attachments(attachment_ids: list, session: AsyncSession) -> list[dict]:
    if not attachment_ids:
        return []
    results = []
    for aid in attachment_ids:
        try:
            asset_uuid = uuid.UUID(str(aid))
        except ValueError:
            continue
        asset = await session.get(Asset, asset_uuid)
        if asset:
            results.append({
                "id": str(asset.id),
                "url": f"/assets/file/{asset.filename}",
                "original_name": asset.original_name,
                "content_type": asset.content_type,
            })
    return results


def serialize_reply(reply: FeedbackReply, author_name: str | None, author_clan_rank: str | None = None) -> dict:
    return {
        "id": reply.id,
        "feedback_id": reply.feedback_id,
        "body": reply.body,
        "is_pinned": reply.is_pinned,
        "author_name": author_name,
        "author_discord_id": reply.discord_user_id,
        "author_clan_rank": author_clan_rank,
        "created_at": reply.created_at.isoformat(),
        "updated_at": reply.updated_at.isoformat(),
    }
