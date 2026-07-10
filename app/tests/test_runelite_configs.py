from __future__ import annotations

from httpx import AsyncClient

_SAMPLE = [
    {
        "regionId": 13395,
        "regionX": 7,
        "regionY": 46,
        "z": 2,
        "color": "#FF000000",
        "label": "Anchor",
    },
    {"regionId": 13395, "regionX": 14, "regionY": 47, "z": 2, "color": "#FFFFFFFF"},
]


async def test_list_configs_public(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/runelite-configs")
    assert resp.status_code == 200


async def test_get_config_public_not_found(anon_client: AsyncClient) -> None:
    resp = await anon_client.get(
        "/runelite-configs/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404


async def test_create_config_requires_staff(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        "/runelite-configs",
        json={"type": "tile_marker", "name": "Test", "data": _SAMPLE},
    )
    assert resp.status_code == 403


async def test_create_config_staff_roundtrip(staff_client: AsyncClient) -> None:
    resp = await staff_client.post(
        "/runelite-configs",
        json={"type": "tile_marker", "name": "Test", "data": _SAMPLE},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == _SAMPLE
    assert body["type"] == "tile_marker"


async def test_create_config_rejects_empty_tile_marker(
    staff_client: AsyncClient,
) -> None:
    resp = await staff_client.post(
        "/runelite-configs",
        json={"type": "tile_marker", "name": "Test", "data": []},
    )
    assert resp.status_code == 422


async def test_update_config_requires_staff(auth_client: AsyncClient) -> None:
    resp = await auth_client.put(
        "/runelite-configs/00000000-0000-0000-0000-000000000000",
        json={"type": "tile_marker", "name": "Test", "data": _SAMPLE},
    )
    assert resp.status_code == 403


async def test_delete_config_requires_staff(auth_client: AsyncClient) -> None:
    resp = await auth_client.delete(
        "/runelite-configs/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 403
