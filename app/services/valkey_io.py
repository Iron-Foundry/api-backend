"""Narrowing helper for valkey-py responses.

valkey-py gives its sync and async clients one shared signature, so a command
returning a concrete type is annotated `Awaitable[T] | T` - `hgetall` is
`Awaitable[dict] | dict`, for example. On the async client it is always the
awaitable branch, but the union still has to be narrowed or the type checker
rejects the `await`. Commands annotated `Awaitable[Any] | Any` need no help,
which is why most of this codebase has never hit it.
"""

from __future__ import annotations

from collections.abc import Awaitable


async def resolve[T](value: Awaitable[T] | T) -> T:
    """Await a valkey response whose annotation carries a non-awaitable branch."""
    if isinstance(value, Awaitable):
        return await value
    return value
