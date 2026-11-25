from fastapi import APIRouter

from app.docs import responses

from .loot import router as loot_router
from .loot_rates import router as loot_rates_router
from .osrs_art import router as osrs_art_router
from .rates import router as rates_router

router = APIRouter(
    prefix="/reference", tags=["reference"], responses=responses.PUBLIC_LOOKUP
)
router.include_router(loot_router)
router.include_router(loot_rates_router)
router.include_router(osrs_art_router)
router.include_router(rates_router)

__all__ = ["router"]
