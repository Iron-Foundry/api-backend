from fastapi import APIRouter

from app.docs import responses

from .collection_log import router as collection_log_router
from .kill_rates import router as kill_rates_router
from .loot_rates import router as loot_rates_router
from .osrs_art import router as osrs_art_router
from .osrs_assets import router as osrs_assets_router
from .rates import router as rates_router

router = APIRouter(
    prefix="/reference", tags=["reference"], responses=responses.PUBLIC_LOOKUP
)
router.include_router(collection_log_router)
router.include_router(kill_rates_router)
router.include_router(loot_rates_router)
router.include_router(osrs_art_router)
router.include_router(osrs_assets_router)
router.include_router(rates_router)

__all__ = ["router"]
