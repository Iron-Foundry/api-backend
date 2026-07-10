"""Sync management endpoints and SSE event stream for real-time tile activity."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.services.page_permissions import require_page_permission

router = APIRouter()


@router.post(
    "/sync",
    dependencies=[Depends(require_page_permission("staff.map_tiles", "create"))],
)
async def start_sync(request: Request, force: bool = False) -> dict:
    """Trigger a background sync of all map tiles from Explv's repository."""
    svc = getattr(request.app.state, "tile_sync_service", None)
    if svc is None:
        raise HTTPException(503, "Tile sync service unavailable")
    return await svc.start(force=force)


@router.post(
    "/sync/stop",
    dependencies=[Depends(require_page_permission("staff.map_tiles", "edit"))],
)
async def stop_sync(request: Request) -> dict:
    """Stop a running background tile sync, wherever it is running."""
    svc = getattr(request.app.state, "tile_sync_service", None)
    if svc is None:
        raise HTTPException(503, "Tile sync service unavailable")
    return await svc.stop()


@router.get(
    "/sync/status",
    dependencies=[Depends(require_page_permission("staff.map_tiles", "read"))],
)
async def sync_status(request: Request) -> dict:
    """Return sync status, cached tile count, and progress detail when running.

    Status is read from Valkey so it is correct regardless of which worker
    is running the sync.
    """
    svc = getattr(request.app.state, "tile_sync_service", None)
    if svc is None:
        return {"running": False, "cached": 0}
    state = await svc.status()
    cached = await svc.cached_count()
    return {**state, "cached": cached}


@router.get("/events")
async def tile_events_stream(request: Request) -> StreamingResponse:
    """SSE stream of real-time tile events. Public endpoint (EventSource cannot send auth headers)."""
    bus = getattr(request.app.state, "tile_event_bus", None)
    if bus is None:
        raise HTTPException(503, "Event bus unavailable")

    async def generate() -> AsyncGenerator[str, None]:
        async for chunk in bus.stream():
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
