"""The `music:events` stream: reading it, and never counting anything twice.

Split from the service so the delivery semantics - which are Valkey behaviour,
not application logic - can be read and tested without a database, a task loop
or a connection policy in the way.

A consumer group delivers at least once: a crash between the write and the
acknowledgement replays the message. Every id is therefore claimed with `SET NX`
before it is counted and released again if the transaction fails, because an
inflated total is worse than a missing one - nothing can audit it back down.
"""

from __future__ import annotations

from typing import Any

from valkey.asyncio import Valkey

STREAM = "music:events"
GROUP = "api-backend"
# One shared consumer name across workers on purpose: whichever worker polls
# next drains what a crashed one left pending, and the claim below is what makes
# that safe rather than double-counted.
CONSUMER = "api-backend"

BATCH = 100

SEEN_KEY = "music:events:seen:{message_id}"
# Long enough to cover any redelivery worth worrying about, short enough that
# the claims expire on their own rather than accumulating forever.
SEEN_TTL_SECONDS = 86_400

Message = tuple[Any, dict[Any, Any]]


def text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def fields(raw: dict[Any, Any]) -> dict[str, str]:
    return {text(key): text(value) for key, value in raw.items()}


async def ensure_group(valkey: Valkey) -> None:
    """Create the group, tolerating the far more common case of it existing."""
    try:
        await valkey.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def read(valkey: Valkey, message_id: str, block_ms: int | None) -> list[Message]:
    """One batch, either this consumer's pending (`0`) or new arrivals (`>`)."""
    response = await valkey.xreadgroup(
        GROUP, CONSUMER, {STREAM: message_id}, count=BATCH, block=block_ms
    )
    return [entry for _, entries in response or [] for entry in entries]


async def claim(valkey: Valkey, message_id: Any) -> bool:
    """Whether this message has not been counted yet."""
    key = SEEN_KEY.format(message_id=text(message_id))
    return bool(await valkey.set(key, "1", nx=True, ex=SEEN_TTL_SECONDS))


async def release(valkey: Valkey, message_ids: list[Any]) -> None:
    """Give the claims back, so a failed batch is counted when it returns."""
    if message_ids:
        await valkey.delete(
            *[SEEN_KEY.format(message_id=text(mid)) for mid in message_ids]
        )


async def ack(valkey: Valkey, message_ids: list[Any]) -> None:
    if message_ids:
        await valkey.xack(STREAM, GROUP, *message_ids)
