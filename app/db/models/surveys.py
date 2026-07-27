from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, BigInteger, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SurveyTemplate(Base):
    __tablename__ = "survey_templates"

    template_id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    questions: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class SurveyActive(Base):
    __tablename__ = "survey_active"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default="1")
    template_id: Mapped[str] = mapped_column(Text, nullable=False)
    ticket_id: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class SurveyResponse(Base):
    __tablename__ = "survey_responses"

    ticket_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[str] = mapped_column(Text, nullable=False)
    responses: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class WebSurveySubmission(Base):
    __tablename__ = "web_survey_submissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    template_id: Mapped[str] = mapped_column(Text, nullable=False)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    answers: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
