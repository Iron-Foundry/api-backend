from fastapi import APIRouter

from .chat import router as chat_router
from .crud import router as crud_router
from .membership import router as membership_router
from .notifications import router as notifications_router

router = APIRouter(prefix="/parties", tags=["parties"])
# notifications must come before /{party_id} to avoid route shadowing
router.include_router(notifications_router)
router.include_router(membership_router)
router.include_router(chat_router)
router.include_router(crud_router)
