# landing_page_app/main.py
from fastapi import FastAPI, Request
from landing_page_app.routers.router import include_routers
from landing_page_app import database
from landing_page_app.database import get_db
from landing_page_app.models.user import User
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
from typing import Generator
from landing_page_app.routers import work_update
from landing_page_app.routers import resume_extract
from landing_page_app.routers.candidates import gmail
from landing_page_app.routers.auth import get_current_user
# ==============================
# Load .env (if python-dotenv available)
# ==============================
# This ensures environment variables such as GOOGLE_CLIENT_ID,
# GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, SMTP_USERNAME, etc.
# are available to your application at runtime.
try:
    from dotenv import load_dotenv
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path) # loads variables from .env into environment
except Exception:
    # python-dotenv not installed or failed to load — continue without crashing.
    # In that case, ensure env vars are provided by your deployment environment.
    pass


# ---------------------------------------------------
# App creation
# ---------------------------------------------------
app = FastAPI(
    title="Landing Page API",
    description="Landing page API with user management",
    version="1.0.0"
)

# ---------------------------------------------------
# Templates folder setup (with global context processor)
# ---------------------------------------------------
templates = Jinja2Templates(directory="landing_page_app/templates")

# ✅ add a global context function so every template automatically
# gets request.state.user injected as "user" even if not passed explicitly.
def inject_user_into_context(request: Request):
    user = getattr(request.state, "user", None)
    return {"user": user}

templates.env.globals["inject_user_into_context"] = inject_user_into_context


# ---------------------------------------------------
# Static mount
# ---------------------------------------------------
app.mount(
    "/static",
    StaticFiles(directory=os.path.join("landing_page_app", "static")),
    name="static"
)

# ---------------------------------------------------
# Database init (dev only)
# ---------------------------------------------------
database.Base.metadata.create_all(bind=database.engine)


# ---------------------------------------------------
# Middleware: attach logged-in user (if present) to request.state.user
# ---------------------------------------------------
@app.middleware("http")
async def attach_user_to_request(request: Request, call_next):
    user_obj = None
    try:
        user_email = request.cookies.get("user_email")
        if user_email:
            gen: Generator = get_db()
            db = next(gen)
            try:
                user_obj = db.query(User).filter(User.email == user_email).first()
            finally:
                try:
                    gen.close()
                except Exception:
                    pass
    except Exception:
        user_obj = None

    request.state.user = user_obj
    response = await call_next(request)
    return response


# ---------------------------------------------------
# Include all routers (delegated to router.py)
# ---------------------------------------------------
include_routers(app)
app.include_router(work_update.router)
app.include_router(resume_extract.router)
app.include_router(gmail.router)