from fastapi import APIRouter

from ._osrs_cache import warm_osrs_caches as warm_osrs_caches
from .draft import router as draft_router
from .draft_picks import router as draft_picks_router
from .event_state import router as event_state_router
from .event_wom import router as event_wom_router
from .events import router as events_router
from .history import router as history_router
from .osrs_ref import router as osrs_ref_router
from .public import router as public_router
from .public_board import router as public_board_router
from .public_team import router as public_team_router
from .signup_list import router as signup_list_router
from .signups import router as signups_router
from .submissions import router as submissions_router
from .teams import router as teams_router
from .template_versions import router as template_versions_router
from .templates import router as templates_router

router = APIRouter(prefix="/frenzy", tags=["frenzy"])

# Public routes first
router.include_router(public_router)
router.include_router(public_board_router)
router.include_router(public_team_router)
router.include_router(history_router)
router.include_router(osrs_ref_router)
router.include_router(signups_router)
router.include_router(draft_picks_router)

# Admin routes
router.include_router(templates_router)
router.include_router(template_versions_router)
router.include_router(events_router)
router.include_router(event_state_router)
router.include_router(event_wom_router)
router.include_router(teams_router)
router.include_router(submissions_router)
router.include_router(signup_list_router)
router.include_router(draft_router)
