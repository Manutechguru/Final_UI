from fastapi import FastAPI, Request, Response, Cookie, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from passlib.hash import bcrypt

from landing_page_app import database
from landing_page_app.routers import jobs, candidates, clients, status_history, templates as template_router
from landing_page_app.models.user import User, UserRole
from landing_page_app.models.log import UserLog
from landing_page_app.routers import admin 
from landing_page_app.routers import auth
# ------------------------------
# Database setup
# ------------------------------
database.Base.metadata.create_all(bind=database.engine)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------------
# FastAPI app setup
# ------------------------------
app = FastAPI(
    title="Landing Page API",
    description="Landing page API with user management",
    version="1.0.0"
)

# Static files
app.mount("/static", StaticFiles(directory="landing_page_app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="landing_page_app/templates")

# ------------------------------
# Root route
# ------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")

# ------------------------------
# User landing page
# ------------------------------
@app.get("/templates", response_class=HTMLResponse)
async def user_landing(request: Request, user_email: str | None = Cookie(None), db: Session = Depends(get_db)):
    if not user_email:
        return RedirectResponse("/login")

    user = db.query(User).filter(User.email == user_email).first()
    if not user or not user.is_active:
        return templates.TemplateResponse("login.html", {"request": request, "message": "Waiting for admin approval"})

    return templates.TemplateResponse("landing.html", {"request": request, "user": user})

# ------------------------------
# Include other routers
# ------------------------------
app.include_router(jobs.router)
app.include_router(candidates.router)
app.include_router(clients.router)
app.include_router(status_history.router)
app.include_router(template_router.router)
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(auth.router, tags=["Auth"])