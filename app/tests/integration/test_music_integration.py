"""Real-DB playlist CRUD, ownership and visibility.

Visibility and ownership are enforced by the queries themselves, so they are
tested against real Postgres rather than a mocked session: a mock would happily
return rows the real filter excludes.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.tests.conftest import TEST_USER

pytestmark = pytest.mark.integration

OWNER = int(TEST_USER["sub"])
STRANGER = 999888777666555444

TRACK: dict[str, Any] = {
    "source": "spotify",
    "identifier": "4b93D55xv3YCH5mT4p6HPn",
    "title": "Zanaris Nocturne",
    "author": "Barbarian Assault",
    "duration_ms": 180_000,
    "isrc": "USABC1234567",
    "uri": "https://open.spotify.com/track/4b93D55xv3YCH5mT4p6HPn",
    "artwork": "https://i.scdn.co/image/4b93D55xv3YCH5mT4p6HPn",
}


def track(index: int) -> dict[str, Any]:
    return {**TRACK, "identifier": f"id-{index}", "title": f"Track {index}"}


@pytest.fixture
def bot_client(app: FastAPI, client: AsyncClient) -> AsyncClient:
    """The same client, with the shared service key accepted.

    The bot surface is guarded by `verify_metrics_key`, not by a user JWT, so
    the user overrides the other fixtures install do not open it.
    """
    from app.dependencies import verify_metrics_key

    app.dependency_overrides[verify_metrics_key] = lambda: None
    return client


async def create(client: AsyncClient, **kwargs: Any) -> dict[str, Any]:
    body = {"name": "Slayer Tunes", "is_public": False, "tracks": [], **kwargs}
    response = await client.post("/music/playlists", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _insert_foreign_playlist(
    engine: AsyncEngine, name: str, is_public: bool
) -> int:
    async with engine.begin() as conn:
        result = await conn.execute(
            sa.text(
                "INSERT INTO playlists (owner_discord_id, name, is_public)"
                " VALUES (:owner, :name, :public) RETURNING id"
            ),
            {"owner": STRANGER, "name": name, "public": is_public},
        )
        return int(result.scalar_one())


async def test_create_returns_the_playlist_with_its_tracks(
    client: AsyncClient,
) -> None:
    body = await create(client, tracks=[track(0), track(1)])

    # A string, because a Discord snowflake does not survive a browser parsing
    # it as a JSON number.
    assert body["owner_discord_id"] == str(OWNER)
    assert body["track_count"] == 2
    assert [t["position"] for t in body["tracks"]] == [0, 1]
    assert body["tracks"][0]["isrc"] == "USABC1234567"


async def test_the_cover_survives_being_saved_and_read_back(
    client: AsyncClient,
) -> None:
    # A saved track re-resolves its audio at play time, and the mirror it
    # resolves to carries someone else's cover, so this is the only copy of the
    # art the user actually picked.
    body = await create(client, tracks=[track(0), {**track(1), "artwork": None}])

    assert body["tracks"][0]["artwork"] == TRACK["artwork"]
    assert body["tracks"][1]["artwork"] is None


async def test_reordering_a_playlist_does_not_drop_the_cover(
    client: AsyncClient,
) -> None:
    # The web writes the whole list back to reorder it, so a field the browser
    # forgets to carry is deleted from the table rather than left alone.
    playlist = await create(client, tracks=[track(0), track(1)])
    rows = list(reversed(playlist["tracks"]))

    response = await client.put(
        f"/music/playlists/{playlist['id']}/tracks", json={"tracks": rows}
    )

    assert response.status_code == 200, response.text
    assert [t["artwork"] for t in response.json()["tracks"]] == [TRACK["artwork"]] * 2


async def test_an_isrc_is_stored_alongside_the_source_identifier(
    client: AsyncClient,
) -> None:
    # Without the ISRC a dead YouTube id would take the track with it.
    body = await create(client, tracks=[track(0)])
    saved = body["tracks"][0]

    assert saved["identifier"] == "id-0"
    assert saved["isrc"] == "USABC1234567"


async def test_a_track_without_an_isrc_is_still_accepted(
    client: AsyncClient,
) -> None:
    body = await create(client, tracks=[{**track(0), "isrc": None}])
    assert body["tracks"][0]["isrc"] is None


async def test_duplicate_names_for_one_owner_are_refused(
    client: AsyncClient,
) -> None:
    await create(client, name="Slayer Tunes")
    response = await client.post(
        "/music/playlists", json={"name": "Slayer Tunes", "tracks": []}
    )

    assert response.status_code == 409


async def test_get_returns_tracks_in_position_order(client: AsyncClient) -> None:
    created = await create(client, tracks=[track(i) for i in range(5)])

    body = (await client.get(f"/music/playlists/{created['id']}")).json()
    assert [t["title"] for t in body["tracks"]] == [f"Track {i}" for i in range(5)]


async def test_rename_and_publish(client: AsyncClient) -> None:
    created = await create(client)

    response = await client.patch(
        f"/music/playlists/{created['id']}",
        json={"name": "Raid Tunes", "is_public": True},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Raid Tunes"
    assert response.json()["is_public"] is True


async def test_delete_removes_the_playlist_and_its_tracks(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    created = await create(client, tracks=[track(0), track(1)])

    assert (await client.delete(f"/music/playlists/{created['id']}")).status_code == 204
    assert (await client.get(f"/music/playlists/{created['id']}")).status_code == 404

    async with seed_engine.begin() as conn:
        left = await conn.execute(sa.text("SELECT count(*) FROM playlist_tracks"))
        assert left.scalar_one() == 0


async def test_replace_tracks_swaps_the_whole_list(client: AsyncClient) -> None:
    created = await create(client, tracks=[track(i) for i in range(4)])

    response = await client.put(
        f"/music/playlists/{created['id']}/tracks",
        json={"tracks": [track(9)]},
    )

    assert response.status_code == 200
    assert [t["title"] for t in response.json()["tracks"]] == ["Track 9"]
    assert [t["position"] for t in response.json()["tracks"]] == [0]


async def test_append_keeps_positions_contiguous(client: AsyncClient) -> None:
    created = await create(client, tracks=[track(0), track(1)])

    response = await client.post(
        f"/music/playlists/{created['id']}/tracks",
        json={"tracks": [track(2), track(3)]},
    )

    assert [t["position"] for t in response.json()["tracks"]] == [0, 1, 2, 3]


async def test_scope_mine_excludes_other_owners(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    await create(client, name="Mine")
    await _insert_foreign_playlist(seed_engine, "Theirs", is_public=True)

    body = (await client.get("/music/playlists", params={"scope": "mine"})).json()
    assert [p["name"] for p in body] == ["Mine"]


async def test_scope_public_excludes_private_playlists(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    await create(client, name="Mine Private", is_public=False)
    await _insert_foreign_playlist(seed_engine, "Theirs Public", is_public=True)

    body = (await client.get("/music/playlists", params={"scope": "public"})).json()
    assert [p["name"] for p in body] == ["Theirs Public"]


async def test_scope_all_is_mine_plus_public(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    await create(client, name="Mine Private", is_public=False)
    await _insert_foreign_playlist(seed_engine, "Theirs Public", is_public=True)
    await _insert_foreign_playlist(seed_engine, "Theirs Private", is_public=False)

    body = (await client.get("/music/playlists")).json()
    assert sorted(p["name"] for p in body) == ["Mine Private", "Theirs Public"]


async def test_someone_elses_private_playlist_reads_as_missing(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    # 404 rather than 403: a private playlist should not confirm it exists.
    playlist_id = await _insert_foreign_playlist(seed_engine, "Secret", is_public=False)

    assert (await client.get(f"/music/playlists/{playlist_id}")).status_code == 404


async def test_a_public_playlist_is_readable_by_anyone(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    playlist_id = await _insert_foreign_playlist(seed_engine, "Shared", is_public=True)

    response = await client.get(f"/music/playlists/{playlist_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Shared"


async def test_a_public_playlist_is_still_not_editable(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    # Public means loadable, never writable. This is the rule most likely to be
    # got wrong, so it is asserted on every write path.
    playlist_id = await _insert_foreign_playlist(seed_engine, "Shared", is_public=True)

    patch = await client.patch(
        f"/music/playlists/{playlist_id}", json={"name": "Hijacked"}
    )
    delete = await client.delete(f"/music/playlists/{playlist_id}")
    put = await client.put(
        f"/music/playlists/{playlist_id}/tracks", json={"tracks": []}
    )
    post = await client.post(
        f"/music/playlists/{playlist_id}/tracks", json={"tracks": [track(0)]}
    )

    assert [
        patch.status_code,
        delete.status_code,
        put.status_code,
        post.status_code,
    ] == [
        403,
        403,
        403,
        403,
    ]


async def test_two_owners_may_reuse_the_same_playlist_name(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    await _insert_foreign_playlist(seed_engine, "Slayer Tunes", is_public=False)

    response = await client.post(
        "/music/playlists", json={"name": "Slayer Tunes", "tracks": []}
    )
    assert response.status_code == 201


async def test_the_bot_surface_sees_what_that_user_would_see(
    client: AsyncClient, bot_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    await create(client, name="Mine Private", is_public=False)
    await _insert_foreign_playlist(seed_engine, "Theirs Public", is_public=True)
    await _insert_foreign_playlist(seed_engine, "Theirs Private", is_public=False)

    body = (await bot_client.get(f"/music/bot/{OWNER}/playlists")).json()
    assert sorted(p["name"] for p in body) == ["Mine Private", "Theirs Public"]


async def test_the_bot_surface_can_narrow_to_that_users_own(
    client: AsyncClient, bot_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    await create(client, name="Mine")
    await _insert_foreign_playlist(seed_engine, "Theirs Public", is_public=True)

    body = (
        await client.get(f"/music/bot/{OWNER}/playlists", params={"mine_only": "true"})
    ).json()
    assert [p["name"] for p in body] == ["Mine"]


async def test_the_bot_surface_will_not_hand_over_a_private_playlist(
    bot_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    # The service key names a user; it does not bypass that user's visibility.
    playlist_id = await _insert_foreign_playlist(seed_engine, "Secret", is_public=False)

    response = await bot_client.get(f"/music/bot/{OWNER}/playlists/{playlist_id}")
    assert response.status_code == 404


async def test_the_bot_surface_returns_tracks_to_load(
    client: AsyncClient, bot_client: AsyncClient
) -> None:
    created = await create(client, tracks=[track(0), track(1)])

    body = (await client.get(f"/music/bot/{OWNER}/playlists/{created['id']}")).json()
    assert [t["identifier"] for t in body["tracks"]] == ["id-0", "id-1"]


async def test_a_missing_playlist_is_404_on_every_route(client: AsyncClient) -> None:
    assert (await client.get("/music/playlists/424242")).status_code == 404
    assert (await client.delete("/music/playlists/424242")).status_code == 404
    assert (
        await client.patch("/music/playlists/424242", json={"name": "x"})
    ).status_code == 404
    assert (
        await client.put("/music/playlists/424242/tracks", json={"tracks": []})
    ).status_code == 404


async def test_an_imported_playlist_lands_as_real_rows(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Lavalink is stubbed; what is asserted is that a link becomes ordered rows
    # in Postgres, named after the source, with the ISRC that lets a dead source
    # id re-resolve later.
    from app.services.lavalink import LoadResult

    async def loaded(*args: Any, **kwargs: Any) -> LoadResult:
        return LoadResult(
            tracks=[
                {
                    "source": "spotify",
                    "identifier": f"imported-{i}",
                    "title": f"Imported {i}",
                    "author": "Barbarian Assault",
                    "duration_ms": 200_000,
                    "isrc": f"USABC000000{i}",
                    "uri": f"https://open.spotify.com/track/imported-{i}",
                }
                for i in range(3)
            ],
            playlist_name="Slayer Tunes",
        )

    monkeypatch.setattr("app.routers.music.importing.load", loaded)
    monkeypatch.setattr("app.routers.music.importing.is_configured", lambda: True)

    response = await client.post(
        "/music/playlists/import",
        json={"url": "https://open.spotify.com/playlist/abc123"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Slayer Tunes"
    assert body["track_count"] == 3
    assert [t["position"] for t in body["tracks"]] == [0, 1, 2]
    assert [t["title"] for t in body["tracks"]] == [
        "Imported 0",
        "Imported 1",
        "Imported 2",
    ]
    assert body["tracks"][0]["isrc"] == "USABC0000000"

    # It is a real playlist afterwards, not just a response body.
    listed = (await client.get("/music/playlists?scope=mine")).json()
    assert any(p["name"] == "Slayer Tunes" for p in listed)


async def test_importing_the_same_name_twice_is_refused(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.lavalink import LoadResult

    async def loaded(*args: Any, **kwargs: Any) -> LoadResult:
        return LoadResult(tracks=[dict(TRACK)], playlist_name="Twice")

    monkeypatch.setattr("app.routers.music.importing.load", loaded)
    monkeypatch.setattr("app.routers.music.importing.is_configured", lambda: True)
    payload = {"url": "https://open.spotify.com/playlist/abc123"}

    assert (
        await client.post("/music/playlists/import", json=payload)
    ).status_code == 201
    assert (
        await client.post("/music/playlists/import", json=payload)
    ).status_code == 409
