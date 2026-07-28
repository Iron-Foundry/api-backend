"""The reference page is only as good as the metadata the schema carries."""

from __future__ import annotations

from httpx import AsyncClient

from app.docs import TAG_GROUPS, TAGS_METADATA
from app.main import app


async def test_info_block_is_populated(anon_client: AsyncClient) -> None:
    info = (await anon_client.get("/openapi.json")).json()["info"]
    assert info["title"] == "The Foundry API"
    assert info["version"] == app.version
    assert "## Authentication" in info["description"]


async def test_servers_are_declared(anon_client: AsyncClient) -> None:
    servers = (await anon_client.get("/openapi.json")).json()["servers"]
    assert [s["url"] for s in servers] == [
        "https://api.ironfoundry.cc",
        "http://localhost:8000",
    ]


async def test_security_schemes_are_declared(anon_client: AsyncClient) -> None:
    schemes = (await anon_client.get("/openapi.json")).json()["components"][
        "securitySchemes"
    ]
    assert schemes["DiscordJWT"] == {
        "type": "http",
        "scheme": "bearer",
        "description": schemes["DiscordJWT"]["description"],
    }
    assert schemes["MemberApiKey"]["in"] == "header"
    assert schemes["MemberApiKey"]["name"] == "verification-code"
    assert schemes["MetricsApiKey"]["name"] == "verification-code"


async def test_every_operation_is_tagged_and_summarised(
    anon_client: AsyncClient,
) -> None:
    paths = (await anon_client.get("/openapi.json")).json()["paths"]
    untagged = [
        f"{method.upper()} {path}"
        for path, ops in paths.items()
        for method, op in ops.items()
        if not op.get("tags") or not op.get("summary")
    ]
    assert not untagged, f"operations missing a tag or summary: {untagged}"


async def test_no_operation_carries_a_duplicate_tag(anon_client: AsyncClient) -> None:
    paths = (await anon_client.get("/openapi.json")).json()["paths"]
    duplicated = [
        f"{method.upper()} {path}"
        for path, ops in paths.items()
        for method, op in ops.items()
        if len(op["tags"]) != len(set(op["tags"]))
    ]
    assert not duplicated, f"parent and child router both tag: {duplicated}"


async def test_every_used_tag_has_a_description(anon_client: AsyncClient) -> None:
    paths = (await anon_client.get("/openapi.json")).json()["paths"]
    used = {tag for ops in paths.values() for op in ops.values() for tag in op["tags"]}
    described = {tag["name"] for tag in TAGS_METADATA}
    assert not used - described, f"tags with no sidebar description: {used - described}"
    assert not described - used, f"described tags no route uses: {described - used}"


async def test_tag_groups_partition_every_tag(anon_client: AsyncClient) -> None:
    grouped = [tag for group in TAG_GROUPS for tag in group["tags"]]
    assert len(grouped) == len(set(grouped)), "a tag appears in two groups"
    assert set(grouped) == {tag["name"] for tag in TAGS_METADATA}


async def test_tag_groups_are_emitted(anon_client: AsyncClient) -> None:
    schema = (await anon_client.get("/openapi.json")).json()
    assert schema["x-tagGroups"] == TAG_GROUPS
