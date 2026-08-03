"""Emptying every table between tests, against an app that never stops writing.

The integration app boots once per worker and keeps its background services
running for the whole session - metrics, party expiry, music stats and the
compaction job all hold the same session factory and write on their own timers.
``TRUNCATE`` takes an AccessExclusiveLock on every table at once, so it
deadlocks whenever one of those transactions already holds a row lock on a table
still ahead in the list. Postgres resolves a deadlock by killing one side, and
which side it picks is arbitrary, so the reset fails at random in whichever test
happened to request it.

Those background transactions are short. Retrying the truncation is what makes
the reset reliable without silencing a background service or weakening the
isolation each test depends on.
"""

from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

ATTEMPTS = 5
BACKOFF_SECONDS = 0.2

# deadlock_detected, lock_not_available (our lock_timeout), serialization_failure
RETRYABLE_STATES = frozenset({"40P01", "55P03", "40001"})


def build_truncate_statement(tables: list[str]) -> str | None:
    if not tables:
        return None
    targets = ", ".join(f'"{table}"' for table in tables)
    return f"TRUNCATE TABLE {targets} RESTART IDENTITY CASCADE"


def lock_error_state(exc: BaseException) -> str | None:
    """The SQLSTATE of a transient lock failure anywhere in the exception chain.

    SQLAlchemy translates the asyncpg error and re-raises it from the original,
    so the code can sit on the wrapper, on ``orig``, or further down the chain.
    """
    seen: set[int] = set()
    pending: list[BaseException | None] = [exc]
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        code = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if code in RETRYABLE_STATES:
            return str(code)
        pending += [
            getattr(current, "orig", None),
            current.__cause__,
            current.__context__,
        ]
    return None


async def truncate_all(engine: AsyncEngine, statement: str) -> None:
    """Empty every table, retrying while a background service holds its locks."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            async with engine.begin() as conn:
                await conn.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
                await conn.execute(sa.text(statement))
            return
        except DBAPIError as exc:
            if lock_error_state(exc) is None or attempt == ATTEMPTS:
                raise
            await asyncio.sleep(BACKOFF_SECONDS * attempt)
