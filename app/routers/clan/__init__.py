from fastapi import APIRouter

from .competition_management import router as comp_mgmt_router
from .competitions import router as competitions_router
from .leaderboards import router as leaderboards_router
from .name_changes import router as name_changes_router
from .stats import router as stats_router

router = APIRouter(prefix="/clan", tags=["clan"])
router.include_router(stats_router)
router.include_router(name_changes_router)
router.include_router(leaderboards_router)
# specific competition paths must come before /{competition_id}
router.include_router(competitions_router)
router.include_router(comp_mgmt_router)
