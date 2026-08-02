"""Real-infra fixtures: boot Postgres + Valkey and run the real app on them.

Unlike the mocked suite in the parent conftest, these fixtures run the actual
`app.main:app` through its lifespan against live Postgres and Valkey, with
Alembic migrations applied. Selected only under `-m integration`.

The endpoints come from the test runner (`TEST_DATABASE_URL` / `TEST_VALKEY_URI`,
one container pair shared by every module) when it supplies them, and from
throwaway testcontainers otherwise, so a hand-run `uv run pytest -m integration`
still works. Each pytest-xdist worker then gets its own cloned database and its
own Valkey logical database - see `_infra`.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Iterator

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.tests.conftest import TEST_USER
from app.tests.integration import _infra as infra

pytestmark = pytest.mark.integration

_docker = pytest.importorskip("docker")
_tc_postgres = pytest.importorskip("testcontainers.postgres")
_tc_container = pytest.importorskip("testcontainers.core.container")
_lifespan = pytest.importorskip("asgi_lifespan")


def _docker_available() -> bool:
    try:
        _docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def _endpoints() -> Iterator[dict[str, str]]:
    runner_db = os.getenv("TEST_DATABASE_URL")
    runner_valkey = os.getenv("TEST_VALKEY_URI")
    if runner_db and runner_valkey:
        yield {"database_url": infra.async_url(runner_db), "valkey_uri": runner_valkey}
        return

    if not _docker_available():
        pytest.skip("Docker is not available for integration tests")

    postgres = _tc_postgres.PostgresContainer("postgres:17-alpine", driver="asyncpg")
    valkey = _tc_container.DockerContainer("valkey/valkey:8-alpine").with_exposed_ports(
        6379
    )
    postgres.start()
    valkey.start()
    try:
        host = valkey.get_container_host_ip()
        port = valkey.get_exposed_port(6379)
        infra.wait_port(host, port)
        yield {
            "database_url": postgres.get_connection_url(),
            "valkey_uri": f"redis://{host}:{port}",
        }
    finally:
        valkey.stop()
        postgres.stop()


@pytest.fixture(scope="session")
def _env(_endpoints: dict[str, str], worker_id: str) -> dict[str, str]:
    """Clone the migrated template into this worker's own database."""
    base_url = _endpoints["database_url"]
    target = infra.worker_database(worker_id)

    def _migrate() -> None:
        from alembic.config import Config

        from alembic import command

        os.environ["DATABASE_URL"] = infra.with_database(base_url, infra.TEMPLATE_DB)
        command.upgrade(Config("alembic.ini"), "head")

    asyncio.run(infra.provision_database(base_url, target, _migrate))

    database_url = infra.with_database(base_url, target)
    valkey_uri = infra.worker_valkey_uri(_endpoints["valkey_uri"], worker_id)
    os.environ["DATABASE_URL"] = database_url
    os.environ["VALKEY_URI"] = valkey_uri
    return {"database_url": database_url, "valkey_uri": valkey_uri}


@pytest.fixture
def db_url(_env: dict[str, str]) -> str:
    return _env["database_url"]


@pytest.fixture(scope="session")
async def engine(_env: dict[str, str]) -> AsyncGenerator[AsyncEngine]:
    """One engine for the whole worker - seeding, asserting and truncation."""
    created = create_async_engine(_env["database_url"])
    try:
        yield created
    finally:
        await created.dispose()


@pytest.fixture(scope="session")
async def _truncate_statement(engine: AsyncEngine) -> str | None:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename != 'alembic_version'"
            )
        )
        return infra.build_truncate_statement(list(result.scalars().all()))


@pytest.fixture
async def _truncate(
    app: FastAPI, engine: AsyncEngine, _truncate_statement: str | None
) -> None:
    """Reset the shared app and empty every table, in a single round trip.

    Every client fixture depends on this, so it is the one place that runs
    before all of them - which is what makes the override reset safe when a
    test pulls in two clients at once.
    """
    app.dependency_overrides.clear()
    if _truncate_statement is None:
        return
    async with engine.begin() as conn:
        await conn.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
        await conn.execute(sa.text(_truncate_statement))


@pytest.fixture
async def seed_engine(engine: AsyncEngine) -> AsyncEngine:
    """A engine bound to this worker, for seeding and asserting."""
    return engine


@pytest.fixture(scope="session")
async def app(_env: dict[str, str]) -> AsyncGenerator[FastAPI]:
    """The real app, booted once per worker.

    Booting the lifespan per test cost ~1.45s each - it opens Postgres and
    Valkey, warms the osrs caches and starts every background service. The
    per-test isolation that matters is the database, which `_truncate` gives.
    """
    from app.main import app as real_app

    async with _lifespan.LifespanManager(real_app):
        yield real_app


def _asgi(app: FastAPI, *, authed: bool) -> AsyncClient:
    """A client onto the shared app. `_truncate` has already reset it."""
    from app.dependencies import get_current_user, get_optional_user

    if authed:
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        app.dependency_overrides[get_optional_user] = lambda: TEST_USER
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    )


@pytest.fixture
async def client(app: FastAPI, _truncate: None) -> AsyncGenerator[AsyncClient]:
    async with _asgi(app, authed=True) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def anon_client(app: FastAPI, _truncate: None) -> AsyncGenerator[AsyncClient]:
    """Unauthenticated client, for asserting what a public surface hands out."""
    async with _asgi(app, authed=False) as ac:
        yield ac


@pytest.fixture
async def staff_client(app: FastAPI, _truncate: None) -> AsyncGenerator[AsyncClient]:
    """Authed client whose permission checks all pass (staff-gated endpoints)."""
    from app.tests._staff_patches import staff_permission_patches

    with staff_permission_patches():
        async with _asgi(app, authed=True) as ac:
            yield ac
    app.dependency_overrides.clear()
