from fastapi import APIRouter

from .crud import router as crud_router

router = APIRouter(prefix="/runelite-configs", tags=["runelite-configs"])
router.include_router(crud_router)
