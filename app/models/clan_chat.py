from pydantic import BaseModel, Field, field_validator

from app.services.parser.broadcast_template import render_broadcast


class ClanChatPayload(BaseModel):
    """Matches the JSON sent by the TrackScape Connector RuneLite plugin."""

    clan_name: str = Field(alias="clan_name")
    sender: str
    message: str
    rank: str
    icon_id: int = Field(default=0, alias="icon_id")
    is_league_world: bool = Field(default=False, alias="is_league_world")

    model_config = {"populate_by_name": True}

    @field_validator("message")
    @classmethod
    def resolve_variable_tags(cls, message: str) -> str:
        return render_broadcast(message)
