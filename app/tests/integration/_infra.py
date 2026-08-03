"""Container, per-worker database and truncation plumbing for the integration suite.

Split out of ``conftest`` so the fixture module stays inside the file-size limit.

The schema is migrated exactly once per Postgres instance into a template
database; every pytest-xdist worker then clones that template, which is a file
copy rather than a 60-revision Alembic run. An advisory lock serialises the
whole provision so concurrent workers cannot race on the template.
"""

from __future__ import annotations

import asyncio
import socket
import time
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

import asyncpg

TEMPLATE_DB = "foundry_tmpl"
MAINTENANCE_DB = "postgres"

_LOCK_KEY = 0x1F0DB
_VALKEY_DB_COUNT = 16


def wait_port(host: str, port: int | str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, int(port)), timeout=2):
                return
        except OSError:
            time.sleep(0.5)
    raise TimeoutError(f"{host}:{port} not accepting connections after {timeout}s")


def with_database(url: str, name: str) -> str:
    return urlunsplit(urlsplit(url)._replace(path=f"/{name}"))


def plain_dsn(url: str) -> str:
    """Strip the SQLAlchemy driver marker - asyncpg wants a bare libpq URL."""
    return url.replace("+asyncpg", "", 1)


def async_url(url: str) -> str:
    """Force the asyncpg driver marker the runner-supplied DSN may not carry."""
    if "+asyncpg" in url:
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def worker_index(worker_id: str) -> int:
    return 0 if worker_id == "master" else int(worker_id.removeprefix("gw")) + 1


def worker_database(worker_id: str) -> str:
    return "foundry_test" if worker_id == "master" else f"foundry_test_{worker_id}"


def worker_valkey_uri(base_uri: str, worker_id: str) -> str:
    """Give each worker its own Valkey logical database.

    Keys are isolated by this; pubsub channels are NOT - they are global to the
    instance, which is why the pubsub tests carry an ``xdist_group`` mark.
    """
    index = worker_index(worker_id) % _VALKEY_DB_COUNT
    return urlunsplit(urlsplit(base_uri)._replace(path=f"/{index}"))


async def provision_database(
    base_url: str, target: str, migrate: Callable[[], None]
) -> None:
    """Ensure the migrated template exists, then clone it into ``target``."""
    conn = await asyncpg.connect(plain_dsn(with_database(base_url, MAINTENANCE_DB)))
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", _LOCK_KEY)
        try:
            await _ensure_template(conn, migrate)
            await conn.execute(f'DROP DATABASE IF EXISTS "{target}" WITH (FORCE)')
            await conn.execute(f'CREATE DATABASE "{target}" TEMPLATE "{TEMPLATE_DB}"')
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", _LOCK_KEY)
    finally:
        await conn.close()


async def _ensure_template(
    conn: asyncpg.Connection, migrate: Callable[[], None]
) -> None:
    exists = await conn.fetchval(
        "SELECT 1 FROM pg_database WHERE datname = $1", TEMPLATE_DB
    )
    if exists:
        return
    await conn.execute(f'CREATE DATABASE "{TEMPLATE_DB}"')
    try:
        # Alembic's env.py drives its own asyncio.run, so it has to leave this
        # thread; a worker thread has no running loop and can nest freely.
        await asyncio.to_thread(migrate)
    except BaseException:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEMPLATE_DB}" WITH (FORCE)')
        raise
