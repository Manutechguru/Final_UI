from fastapi import APIRouter

# Import sub-routers
from .base import router as base_router
from .jobs import router as jobs_router

# Create parent clients router
router = APIRouter(prefix="/clients", tags=["Clients"])

# Include sub-routers
router.include_router(base_router)
router.include_router(jobs_router)
