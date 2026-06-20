from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field


def _coerce_str(v: object) -> str:
    return str(v)


class ChannelEntry(BaseModel):
    channel_id: Annotated[str, BeforeValidator(_coerce_str)]
    description: str = ""
    emoji: str = ""


class LinkEntry(BaseModel):
    label: str
    url: str


class HeaderImageSection(BaseModel):
    type: Literal["header_image"] = "header_image"
    image_url: str = ""


class ServerStatsSection(BaseModel):
    type: Literal["server_stats"] = "server_stats"


class FreeTextSection(BaseModel):
    type: Literal["free_text"] = "free_text"
    content: str = ""


class ChannelTocSection(BaseModel):
    type: Literal["channel_toc"] = "channel_toc"
    channels: list[ChannelEntry] = Field(default_factory=list)


class NameChangesSection(BaseModel):
    type: Literal["name_changes"] = "name_changes"
    count: int = 5


class AchievementsSection(BaseModel):
    type: Literal["achievements"] = "achievements"
    count: int = 5


class WebsiteLinksSection(BaseModel):
    type: Literal["website_links"] = "website_links"
    links: list[LinkEntry] = Field(default_factory=list)


class PersonalBestsSection(BaseModel):
    type: Literal["personal_bests"] = "personal_bests"
    count: int = 5


class CompetitionsSection(BaseModel):
    type: Literal["competitions"] = "competitions"


SectionConfig = Annotated[
    HeaderImageSection
    | ServerStatsSection
    | FreeTextSection
    | ChannelTocSection
    | NameChangesSection
    | AchievementsSection
    | WebsiteLinksSection
    | PersonalBestsSection
    | CompetitionsSection,
    Field(discriminator="type"),
]


class PanelMessage(BaseModel):
    sections: list[SectionConfig] = Field(default_factory=list)


def _default_messages() -> list[PanelMessage]:
    return [
        PanelMessage(
            sections=[
                ServerStatsSection(),
                CompetitionsSection(),
                NameChangesSection(),
                AchievementsSection(),
                PersonalBestsSection(),
                ChannelTocSection(),
                WebsiteLinksSection(),
                FreeTextSection(),
                HeaderImageSection(),
            ]
        )
    ]


class InfoPanelConfig(BaseModel):
    channel_id: int | None = None
    refresh_interval_minutes: int = 30
    messages: list[PanelMessage] = Field(default_factory=_default_messages)
