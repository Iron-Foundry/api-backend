"""Real-infra fixtures: boot Postgres + Valkey containers and the real app.

Unlike the mocked suite in the parent conftest, these fixtures run the actual
`app.main:app` through its lifespan against live Postgres and Valkey containers,
with Alembic migrations applied. Selected only under `-m integration`.

Each async context builds its own short-lived engine so no asyncpg engine is
ever shared across event loops.
"""

from __future__ import annotations

import os
import socket
import time
from collections.abc import AsyncGenerator, Iterator

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.tests.conftest import TEST_USER

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


def _wait_port(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, int(port)), timeout=2):
                return
        except OSError:
            time.sleep(0.5)
    raise TimeoutError(f"{host}:{port} not accepting connections after {timeout}s")


@pytest.fixture(scope="session")
def _infra() -> Iterator[dict[str, str]]:
    if not _docker_available():
        pytest.skip("Docker is not available for integration tests")

    postgres = _tc_postgres.PostgresContainer("postgres:17-alpine", driver="asyncpg")
    valkey = _tc_container.DockerContainer("valkey/valkey:8-alpine").with_exposed_ports(
        6379
    )
    postgres.start()
    valkey.start()
    try:
        valkey_host = valkey.get_container_host_ip()
        valkey_port = valkey.get_exposed_port(6379)
        _wait_port(valkey_host, valkey_port)
        database_url = postgres.get_connection_url()
        valkey_uri = f"redis://{valkey_host}:{valkey_port}"
        os.environ["DATABASE_URL"] = database_url
        os.environ["VALKEY_URI"] = valkey_uri

        from alembic.config import Config

        from alembic import command

        command.upgrade(Config("alembic.ini"), "head")

        yield {"database_url": database_url, "valkey_uri": valkey_uri}
    finally:
        valkey.stop()
        postgres.stop()


@pytest.fixture
def db_url(_infra: dict[str, str]) -> str:
    return _infra["database_url"]


@pytest.fixture
async def _truncate(db_url: str) -> AsyncGenerator[None]:
    yield
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            tables = (
                (
                    await conn.execute(
                        sa.text(
                            "SELECT tablename FROM pg_tables WHERE schemaname = "
                            "'public' AND tablename != 'alembic_version'"
                        )
                    )
                )
                .scalars()
                .all()
            )
            for table in tables:
                await conn.execute(
                    sa.text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE')
                )
    finally:
        await engine.dispose()


@pytest.fixture
async def app(_infra: dict[str, str]) -> AsyncGenerator[FastAPI]:
    from app.main import app as real_app

    async with _lifespan.LifespanManager(real_app):
        yield real_app


@pytest.fixture
async def client(app: FastAPI, _truncate: None) -> AsyncGenerator[AsyncClient]:
    from app.dependencies import get_current_user, get_optional_user

    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    app.dependency_overrides[get_optional_user] = lambda: TEST_USER
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def staff_client(app: FastAPI, _truncate: None) -> AsyncGenerator[AsyncClient]:
    """Authed client whose permission checks all pass (staff-gated endpoints)."""
    from app.dependencies import get_current_user, get_optional_user
    from app.tests._staff_patches import staff_permission_patches

    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    app.dependency_overrides[get_optional_user] = lambda: TEST_USER
    with staff_permission_patches():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as ac:
            yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def seed_engine(db_url: str) -> AsyncGenerator[AsyncEngine]:
    """A short-lived engine bound to this test's event loop for seeding/asserting."""
    engine = create_async_engine(db_url)
    try:
        yield engine
    finally:
        await engine.dispose()
