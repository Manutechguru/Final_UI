from fastapi import APIRouter

# Import individual candidate routers
from .search import router as search_router
from .link import router as link_router
from .downloads import router as downloads_router

# Create a parent router for candidates
router = APIRouter(prefix="/candidates", tags=["Candidates"])

# Include all sub-routers here
router.include_router(search_router)
router.include_router(link_router)
router.include_router(downloads_router)
