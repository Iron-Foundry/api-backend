from fastapi import APIRouter

from .completions import router as completions_router
from .controls import router as controls_router
from .events import router as events_router
from .osrs_ref import router as osrs_ref_router
from .repository import router as repository_router
from .rolls import router as rolls_router
from .sabotage import router as sabotage_router
from .signups import router as signups_router
from .teams import router as teams_router

router = APIRouter(prefix="/tilerace", tags=["tilerace"])

router.include_router(events_router)
router.include_router(osrs_ref_router)
router.include_router(repository_router)
router.include_router(teams_router)
router.include_router(signups_router)
router.include_router(controls_router)
router.include_router(completions_router)
router.include_router(rolls_router)
router.include_router(sabotage_router)
