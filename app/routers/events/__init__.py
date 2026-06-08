from fastapi import APIRouter

from .ingest import router as ingest_router

router = APIRouter(tags=["clan"])
router.include_router(ingest_router)
