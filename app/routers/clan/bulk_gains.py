from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.services.bulk_gains import BulkGainsService
from app.services.page_permissions import require_page_permission

router = APIRouter()


def _get_service(request: Request) -> BulkGainsService:
    svc = getattr(request.app.state, "bulk_gains_service", None)
    if svc is None:
        raise HTTPException(503, "Bulk gains service not available")
    return svc


class FetchBulkGainsBody(BaseModel):
    period: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None


@router.post(
    "/bulk-gains/fetch",
    status_code=201,
    dependencies=[Depends(require_page_permission("staff.bulk_gains", "trigger"))],
)
async def fetch_bulk_gains(
    body: FetchBulkGainsBody,
    request: Request,
) -> dict:
    if not body.period and not (body.start_date and body.end_date):
        raise HTTPException(
            422, "Provide either period or both start_date and end_date"
        )
    svc = _get_service(request)
    count = await svc.fetch_and_store(
        period=body.period,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    return {"players_stored": count}


@router.get("/bulk-gains/batches")
async def list_bulk_gains_batches(request: Request) -> list[dict]:
    svc = _get_service(request)
    batches = await svc.list_batches()
    return [
        {
            "id": b.id,
            "period": b.period,
            "start_date": b.start_date,
            "end_date": b.end_date,
            "captured_at": b.captured_at,
        }
        for b in batches
    ]


@router.get("/bulk-gains/batches/{batch_id}")
async def get_bulk_gains_batch(batch_id: int, request: Request) -> dict:
    svc = _get_service(request)
    players = await svc.get_batch_players(batch_id)
    if not players:
        raise HTTPException(404, "Batch not found or empty")
    return {
        "batch_id": batch_id,
        "player_count": len(players),
        "players": [
            {
                "rsn": p.rsn,
                "gains_start": p.gains_start,
                "gains_end": p.gains_end,
                "skills": p.skills,
                "bosses": p.bosses,
                "activities": p.activities,
            }
            for p in players
        ],
    }


@router.get("/bulk-gains/batches/{batch_id}/players/{rsn}")
async def get_player_bulk_gains(batch_id: int, rsn: str, request: Request) -> dict:
    svc = _get_service(request)
    row = await svc.get_player_gains(batch_id, rsn)
    if not row:
        raise HTTPException(404, "Player gains not found in this batch")
    return {
        "batch_id": batch_id,
        "rsn": row.rsn,
        "gains_start": row.gains_start,
        "gains_end": row.gains_end,
        "skills": row.skills,
        "bosses": row.bosses,
        "activities": row.activities,
    }
