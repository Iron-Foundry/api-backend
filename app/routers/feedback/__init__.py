from fastapi import APIRouter

from .items import router as items_router
from .replies_reactions import router as replies_reactions_router

router = APIRouter(prefix="/feedback", tags=["feedback"])
router.include_router(items_router)
router.include_router(replies_reactions_router)
