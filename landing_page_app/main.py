# landing_page_app/main.py
from fastapi import FastAPI
from landing_page_app.routers.router import include_routers
from landing_page_app import database

# Create app
app = FastAPI(
    title="Landing Page API",
    description="Landing page API with user management",
    version="1.0.0"
)

# Database init (dev only; use Alembic in prod)
database.Base.metadata.create_all(bind=database.engine)

# Include all routers (delegated to router.py)
include_routers(app)
