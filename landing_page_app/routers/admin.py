from fastapi import APIRouter, Depends, Request, Response, Cookie, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from landing_page_app.database import get_db
from landing_page_app.models.user import User, UserRole
from landing_page_app.models.log import UserLog
from fastapi.templating import Jinja2Templates
import logging

router = APIRouter()
templates = Jinja2Templates(directory="landing_page_app/templates")

# ------------------------------
# Admin dashboard
# ------------------------------

@router.get("/", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    user_email: str | None = Cookie(None),
    db: Session = Depends(get_db),
    msg: str | None = Query(None),
    error: str | None = Query(None),
    duplicates: str | None = Query(None)
):

    if not user_email:
        return RedirectResponse("/auth/login")

    admin = db.query(User).filter(User.email == user_email, User.role == UserRole.ADMIN).first()
    if not admin:
        return RedirectResponse("/auth/login")

    # Pending users
    pending_users = db.query(User).filter(User.is_active == False, User.role == UserRole.USER).all()
    # All users
    all_users = db.query(User).filter(User.role == UserRole.USER).all()
    # User logs
    user_logs = db.query(UserLog).order_by(UserLog.timestamp.desc()).all()

    return templates.TemplateResponse(
        "admindashboard.html",
        {
            "request": request,
            "admin": admin,
            "pending_users": pending_users,
            "all_users": all_users,
            "user_logs": user_logs,
            "msg": msg,
            "error": error,
            "duplicates": duplicates.split(",") if duplicates else []
        }
    )
# ------------------------------
# Approve user
# ------------------------------
@router.post("/approve/{user_id}")
def approve_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_active = True
        db.commit()
        log = UserLog(user_id=user.id, action="APPROVED")
        db.add(log)
        db.commit()
    return RedirectResponse("/admin", status_code=303)

# ------------------------------
# Reject user
# ------------------------------
@router.post("/reject/{user_id}")
def reject_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        log = UserLog(user_id=user.id, action="REJECTED")
        db.add(log)
        db.commit()
        db.delete(user)
        db.commit()
    return RedirectResponse("/admin", status_code=303)

# ------------------------------
# Remove user (existing approved user)
# ------------------------------
@router.post("/remove/{user_id}")
def remove_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        db.add(UserLog(user_id=user.id, action="REMOVED"))
        db.delete(user)
        db.commit()
    return RedirectResponse("/admin", status_code=303)

# ------------------------------
# Admin logout
# ------------------------------
@router.get("/logout")
def admin_logout(response: Response):
    response = RedirectResponse("/auth/login")
    response.delete_cookie("user_email")
    return response

