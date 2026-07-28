from fastapi import APIRouter

from app.docs import responses

from .history import router as history_router
from .report import router as report_router
from .services import router as services_router

router = APIRouter(tags=["metrics"], responses=responses.STAFF)
router.include_router(report_router)
router.include_router(services_router)
router.include_router(history_router)
