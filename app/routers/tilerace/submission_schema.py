from __future__ import annotations

from pydantic import BaseModel, Field


class SubmissionCreateBody(BaseModel):
    """One proof post covering one or more of a tile's requirement leaves."""

    discord_user_id: str
    path_position: int
    leaf_keys: list[str] = Field(min_length=1)
    proof_urls: list[str] = []
    discord_thread_id: str | None = None


class SubmissionReviewBody(BaseModel):
    status: str
    review_notes: str | None = None
    reviewed_by: str | None = None
