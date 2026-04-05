import json

from valkey.asyncio import Valkey

STREAM_KEY = "foundry:clan_events"


async def publish(valkey: Valkey, event_type: str, data: dict) -> None:
    """Publish a clan event to the Valkey stream."""
    await valkey.xadd(STREAM_KEY, {"type": event_type, "data": json.dumps(data)})
