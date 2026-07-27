from fastapi import APIRouter

from ._profile_route import router as profile_router
from .admin import router as admin_router
from .players import router as players_router
from .stats import router as stats_router

router = APIRouter(prefix="/ranking", tags=["ranking"])
router.include_router(stats_router)
router.include_router(players_router)
router.include_router(profile_router)
router.include_router(admin_router)
