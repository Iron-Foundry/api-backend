from fastapi import APIRouter

from .files import router as files_router
from .manage import router as manage_router

router = APIRouter()
router.include_router(files_router)
router.include_router(manage_router)
