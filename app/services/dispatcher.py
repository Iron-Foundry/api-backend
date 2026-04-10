import hashlib
import json

from valkey.asyncio import Valkey

STREAM_KEY = "foundry:clan_events"
_DEDUP_TTL = 5  # seconds


async def is_duplicate(
    valkey: Valkey, verification_code: str, sender: str, message: str
) -> bool:
    """Two-stage dedup. Returns True if payload should be dropped."""
    fp = hashlib.sha256(f"{sender}:{message}".encode()).hexdigest()
    key2 = f"foundry:dedup:client:{hashlib.sha256(f'{verification_code}:{sender}:{message}'.encode()).hexdigest()}"
    key1 = f"foundry:dedup:content:{fp}"

    # Same client already sent this → allow (separate dispatch)
    if await valkey.set(key2, "1", nx=True, ex=_DEDUP_TTL) is None:
        return False

    # Different client already processed this content → drop
    if await valkey.set(key1, "1", nx=True, ex=_DEDUP_TTL) is None:
        return True

    return False  # First time seen


async def publish(valkey: Valkey, event_type: str, data: dict) -> None:
    """Publish a clan event to the Valkey stream."""
    await valkey.xadd(STREAM_KEY, {"type": event_type, "data": json.dumps(data)})
