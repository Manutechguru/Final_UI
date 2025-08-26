from fastapi import APIRouter, Request, Depends, Form, Response, Cookie, Form, HTTPException
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
    response.set_cookie(key="user_email", value=user.email)
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