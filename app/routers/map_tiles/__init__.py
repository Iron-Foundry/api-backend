"""OSRS map tile proxy and sync management - router assembly."""

from fastapi import APIRouter

from .management import router as management_router
from .serve import router as serve_router
from .sync import router as sync_router

router = APIRouter(prefix="/tiles", tags=["map-tiles"])
router.include_router(sync_router)
router.include_router(management_router)
router.include_router(serve_router)
