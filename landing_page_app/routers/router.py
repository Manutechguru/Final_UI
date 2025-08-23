from fastapi import FastAPI, Request, Cookie, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from landing_page_app.core.settings import settings
from landing_page_app.routers import auth, admin, candidates, clients, jobs

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="Landing Page API for jobs, clients, and candidates",
        version="1.0.0"
    )

    # Serve static files
    app.mount("/static", StaticFiles(directory="landing_page_app/static"), name="static")

    # Templates
    templates = Jinja2Templates(directory="landing_page_app/templates")

    # Root redirects to login
    @app.get("/", response_class=HTMLResponse)
    async def root():
        return RedirectResponse(url="/login")

    # Login page
    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return templates.TemplateResponse("login.html", {"request": request})

    # Signup page
    @app.get("/signup", response_class=HTMLResponse)
    async def signup_page(request: Request):
        return templates.TemplateResponse("signup.html", {"request": request})

    # Landing page for normal users
    @app.get("/landing", response_class=HTMLResponse)
    async def landing_page(request: Request, user: str | None = Cookie(None)):
        if user != "user":
            return RedirectResponse(url="/login")
        return templates.TemplateResponse("landing.html", {"request": request})

    # Admin dashboard
    @app.get("/admin/dashboard", response_class=HTMLResponse)
    async def admin_dashboard(request: Request, user: str | None = Cookie(None)):
        if user != "admin":
            return RedirectResponse(url="/login")
        return templates.TemplateResponse("admindashboard.html", {"request": request})

    # Optional: other protected pages
    @app.get("/search", response_class=HTMLResponse)
    async def search_page(request: Request, user: str | None = Cookie(None)):
        if user not in ["user", "admin"]:
            return RedirectResponse(url="/login")
        return templates.TemplateResponse("search.html", {"request": request})

    @app.get("/clients/new-arrivals", response_class=HTMLResponse)
    async def clients_new_arrivals(request: Request, user: str | None = Cookie(None)):
        if user not in ["user", "admin"]:
            return RedirectResponse(url="/login")
        return templates.TemplateResponse("clients_new_arrivals.html", {"request": request})

    # Include routers
    app.include_router(auth.router, prefix="/routers/auth", tags=["auth"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(candidates.router, prefix="/candidates", tags=["candidates"])
    app.include_router(clients.router, prefix="/clients", tags=["clients"])
    app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])

    return app

# Initialize app
app = create_app()
