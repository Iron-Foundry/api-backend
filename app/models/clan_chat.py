from pydantic import BaseModel, Field


class ClanChatPayload(BaseModel):
    """Matches the JSON sent by the TrackScape Connector RuneLite plugin."""

    clan_name: str = Field(alias="clan_name")
    sender: str
    message: str
    rank: str
    icon_id: int = Field(default=0, alias="icon_id")
    is_league_world: bool = Field(default=False, alias="is_league_world")

    model_config = {"populate_by_name": True}
