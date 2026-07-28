from fastapi import APIRouter

from app.docs import responses

from .items import router as items_router
from .replies_reactions import router as replies_reactions_router

router = APIRouter(
    prefix="/feedback", tags=["feedback"], responses=responses.AUTHENTICATED_LOOKUP
)
router.include_router(items_router)
router.include_router(replies_reactions_router)
