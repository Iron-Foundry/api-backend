from fastapi import APIRouter

from .completions import router as completions_router
from .controls import router as controls_router
from .discord_setup import router as discord_setup_router
from .events import router as events_router
from .generate import router as generate_router
from .osrs_ref import router as osrs_ref_router
from .recap import router as recap_router
from .repository import router as repository_router
from .rolls import router as rolls_router
from .roster import router as roster_router
from .roster_lookup import router as roster_lookup_router
from .sabotage import router as sabotage_router
from .signups import router as signups_router
from .submissions import router as submissions_router
from .submissions_review import router as submissions_review_router
from .teams import router as teams_router

router = APIRouter(prefix="/tilerace", tags=["tilerace"])

router.include_router(events_router)
router.include_router(recap_router)
router.include_router(osrs_ref_router)
router.include_router(repository_router)
router.include_router(generate_router)
router.include_router(teams_router)
router.include_router(roster_lookup_router)
router.include_router(roster_router)
router.include_router(signups_router)
router.include_router(controls_router)
router.include_router(completions_router)
router.include_router(submissions_router)
router.include_router(submissions_review_router)
router.include_router(rolls_router)
router.include_router(sabotage_router)
router.include_router(discord_setup_router)
