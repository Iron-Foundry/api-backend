from fastapi import APIRouter

from .accounts import router as accounts_router
from .api_keys import router as api_keys_router
from .feed import router as feed_router
from .profile import router as profile_router
from .rsn import router as rsn_router
from .goals import router as goals_router
from .snapshot import router as snapshot_router
from .tickets import router as tickets_router

router = APIRouter(prefix="/members", tags=["members"])
router.include_router(profile_router)
router.include_router(api_keys_router)
router.include_router(feed_router)
router.include_router(tickets_router)
router.include_router(rsn_router)
router.include_router(accounts_router)
router.include_router(snapshot_router)
router.include_router(goals_router)
