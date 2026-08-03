"""The between-test reset must survive the app's own background writers.

The integration app runs for the whole session, so its metrics and expiry
services hold row locks while TRUNCATE wants an AccessExclusiveLock on every
table. Postgres calls that a deadlock and kills one side at random, which failed
whichever test happened to be resetting. These pin the retry that absorbs it.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.tests.integration._truncation import (
    ATTEMPTS,
    build_truncate_statement,
    lock_error_state,
    truncate_all,
)

_STATEMENT = 'TRUNCATE TABLE "metrics" RESTART IDENTITY CASCADE'


def _pg_error(sqlstate: str) -> DBAPIError:
    """A DBAPIError shaped like the one asyncpg's error translation raises."""
    original = Exception(f"deadlock detected ({sqlstate})")
    original.sqlstate = sqlstate  # type: ignore[attr-defined]
    return DBAPIError("TRUNCATE ...", None, original)


class _Begin:
    """The async context ``engine.begin()`` hands back."""

    def __init__(self, attempts: list[str], pending: list[BaseException]) -> None:
        self._attempts = attempts
        self._pending = pending

    async def __aenter__(self) -> Any:
        self._attempts.append("begin")
        if self._pending:
            raise self._pending.pop(0)
        return AsyncMock()

    async def __aexit__(self, *_exc: Any) -> bool:
        return False


def _engine(failures: list[BaseException]) -> tuple[Any, list[str]]:
    """An engine whose ``begin()`` raises each queued error, then succeeds."""
    attempts: list[str] = []
    pending = list(failures)

    engine = MagicMock()
    engine.begin = lambda: _Begin(attempts, pending)
    return engine, attempts


def test_the_statement_names_every_table_and_resets_identities() -> None:
    assert build_truncate_statement(["metrics", "users"]) == (
        'TRUNCATE TABLE "metrics", "users" RESTART IDENTITY CASCADE'
    )
    assert build_truncate_statement([]) is None


def test_a_deadlock_is_recognised_through_the_wrapper() -> None:
    assert lock_error_state(_pg_error("40P01")) == "40P01"
    assert lock_error_state(_pg_error("55P03")) == "55P03"
    assert lock_error_state(_pg_error("40001")) == "40001"


def test_an_unrelated_database_error_is_not_treated_as_a_lock_failure() -> None:
    assert lock_error_state(_pg_error("23505")) is None
    assert lock_error_state(IntegrityError("insert", None, Exception("dupe"))) is None


async def test_a_deadlocked_reset_is_retried_until_it_lands() -> None:
    engine, attempts = _engine([_pg_error("40P01"), _pg_error("40P01")])

    await truncate_all(engine, _STATEMENT)

    assert len(attempts) == 3, "the reset gave up while the lock was still transient"


async def test_a_reset_that_never_gets_the_lock_still_fails_the_run() -> None:
    engine, attempts = _engine([_pg_error("40P01")] * (ATTEMPTS + 2))

    with pytest.raises(DBAPIError):
        await truncate_all(engine, _STATEMENT)

    assert len(attempts) == ATTEMPTS, (
        "a permanently locked table must not retry forever"
    )


async def test_an_error_that_is_not_a_lock_failure_is_raised_at_once() -> None:
    engine, attempts = _engine([_pg_error("23505")] * 3)

    with pytest.raises(DBAPIError):
        await truncate_all(engine, _STATEMENT)

    assert len(attempts) == 1, "a real failure was retried instead of surfacing"
