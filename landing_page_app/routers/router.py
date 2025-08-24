# landing_page_app/routers/router.py
from fastapi import FastAPI, Request, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from landing_page_app.routers import auth, admin, candidates, clients, jobs, status_history, templates as template_router
from landing_page_app.database import get_db
from landing_page_app.models.user import User
from sqlalchemy.orm import Session
from fastapi import Depends
from landing_page_app.routers import uploadCSV

def include_routers(app: FastAPI):
    # Serve static files
    app.mount("/static", StaticFiles(directory="landing_page_app/static"), name="static")

    # Templates
    templates = Jinja2Templates(directory="landing_page_app/templates")

    # ------------------------------
    # Root redirects to login
    # ------------------------------
    @app.get("/", response_class=HTMLResponse)
    async def root():
        return RedirectResponse(url="/login")

    # ------------------------------
    # User landing page (protected)
    # ------------------------------
    @app.get("/landing", response_class=HTMLResponse)
    async def landing_page(
        request: Request,
        user_email: str | None = Cookie(None),
        db: Session = Depends(get_db)
    ):
        if not user_email:
            return RedirectResponse("/login")

        user = db.query(User).filter(User.email == user_email).first()
        if not user or not user.is_active:
            return templates.TemplateResponse("login.html", {"request": request, "message": "Waiting for admin approval"})

        return templates.TemplateResponse("landing.html", {"request": request, "user": user})

    # ------------------------------
    # Extra protected pages
    # ------------------------------
    @app.get("/search", response_class=HTMLResponse)
    async def search_page(request: Request, user_email: str | None = Cookie(None)):
        if not user_email:
            return RedirectResponse("/login")
        return templates.TemplateResponse("search.html", {"request": request})

    @app.get("/clients/new-arrivals", response_class=HTMLResponse)
    async def clients_new_arrivals(request: Request, user_email: str | None = Cookie(None)):
        if not user_email:
            return RedirectResponse("/login")
        return templates.TemplateResponse("clients_new_arrivals.html", {"request": request})

    # ------------------------------
    # Include routers
    # ------------------------------
    app.include_router(auth.router, tags=["Auth"])
    app.include_router(admin.router, prefix="/admin", tags=["Admin"])
    app.include_router(candidates.router, prefix="/candidates", tags=["Candidates"])
    app.include_router(clients.router, prefix="/clients", tags=["Clients"])
    app.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
    app.include_router(status_history.router, prefix="/status", tags=["Status History"])
    app.include_router(template_router.router, prefix="/templates", tags=["Templates"])
    app.include_router(uploadCSV.router)