# landing_page_app/routers/auth.py
from fastapi import APIRouter, Request, Depends, Form, Response, Cookie, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from landing_page_app.database import get_db
from landing_page_app.models.user import User, UserRole
from landing_page_app.models.log import UserLog

from fastapi.templating import Jinja2Templates
import bcrypt
import os

router = APIRouter()
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ------------------------------
# Signup
# ------------------------------
@router.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@router.post("/signup")
async def signup(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Check if email already exists
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": "Email already registered"}
        )

    # Assign role: admin@example.com → ADMIN, else USER
    role = UserRole.ADMIN if email == "admin@example.com" else UserRole.USER

    # Hash password
    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Create user
    user = User(
        full_name=full_name,
        email=email,
        hashed_password=hashed_pw,
        role=role,
        is_active=(role == UserRole.ADMIN)  # auto-active if admin
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Log signup
    log = UserLog(user_id=user.id, action="SIGNUP")
    db.add(log)
    db.commit()

    return RedirectResponse("/login", status_code=303)

# ------------------------------
# Login
# ------------------------------

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()

    if not user or not bcrypt.checkpw(password.encode("utf-8"), user.hashed_password.encode("utf-8")):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials"}
        )

    if not user.is_active and user.role != UserRole.ADMIN:
        return templates.TemplateResponse("login.html", {"request": {}, "error": "Waiting for admin approval"})
    
    # Log login
    log = UserLog(user_id=user.id, action="LOGIN")
    db.add(log)
    db.commit()

    redirect_url = "/admin" if user.role == UserRole.ADMIN else "/templates"
    response = RedirectResponse(url=redirect_url, status_code=303)

    # -----------------------
    # Cookie flags: choose conservative defaults for localhost and secure defaults for production
    # - When developing on localhost/127.0.0.1: use SameSite=Lax and secure=False (works on http://localhost)
    # - In production (non-localhost) prefer SameSite=None and secure=True (required for cross-site OAuth on HTTPS)
    # You can override behavior by setting COOKIE_SECURE env var to "True" or "False" if desired.
    # -----------------------
    try:
        host = (request.url.hostname or "").lower()
    except Exception:
        host = ""

    is_localhost = host in ("localhost", "127.0.0.1", "0.0.0.0")

    # If an explicit env override exists, use it. Otherwise auto-detect from host.
    cookie_secure_env = os.getenv("COOKIE_SECURE")
    if cookie_secure_env is not None:
        cookie_secure = cookie_secure_env.lower() in ("1", "true", "yes")
    else:
        cookie_secure = not is_localhost

    # Choose SameSite policy appropriate to environment
    if is_localhost:
        cookie_samesite = "Lax"     # local dev: Lax is more permissive for redirects on localhost
    else:
        cookie_samesite = "None"    # production: None required for third-party redirects (must be secure=True)

    # Set cookie (minimal change: only cookie flags adjusted)
    # max_age optional (here 7 days)
    response.set_cookie(
        key="user_email",
        value=user.email,
        httponly=True,
        samesite=cookie_samesite,
        secure=cookie_secure,
        max_age=60 * 60 * 24 * 7
    )
    return response

# ------------------------------
# Logout
# ------------------------------

@router.get("/logout", response_class=HTMLResponse)
async def logout(
    request: Request,
    response: Response,
    user_email: str | None = Cookie(None),
    db: Session = Depends(get_db)
):
    if user_email:
        user = db.query(User).filter(User.email == user_email).first()
        if user:
            log = UserLog(user_id=user.id, action="LOGOUT")
            db.add(log)
            db.commit()

    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("user_email")
    return response


def get_current_user(
    user_email: str | None = Cookie(None),
    db: Session = Depends(get_db)
) -> User:
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
