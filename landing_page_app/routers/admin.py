# landing_page_app/routers/admin.py
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_, func
from fastapi import APIRouter, Depends, Request, Cookie, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from landing_page_app.database import get_db
from landing_page_app.models.user import User, UserRole
from landing_page_app.models.log import UserLog
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="landing_page_app/templates")

# ------------------------------
# Admin dashboard (includes tabs + logs)
# ------------------------------
@router.get("/", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    user_email: str | None = Cookie(None),
    db: Session = Depends(get_db),

    # CSV upload feedback
    msg: str | None = Query(None),
    error: str | None = Query(None),
    duplicates: str | None = Query(None),

    # which tab to show on load
    tab: str = Query("pending"),

    # LOGS: filters + pagination
    log_days: int = Query(2, ge=1, le=30),
    q: str | None = Query(None),                 # search by username/action
    action_filter: str | None = Query(None),     # APPROVED / REJECTED / REMOVED / etc.
    log_skip: int = Query(0, ge=0),
    log_limit: int = Query(20, ge=1, le=200),
):
    # --- Auth guard ---
    if not user_email:
        return RedirectResponse("/auth/login")
    admin = (
        db.query(User)
        .filter(User.email == user_email, User.role == UserRole.ADMIN)
        .first()
    )
    if not admin:
        return RedirectResponse("/auth/login")

    # --- Pending & All Users ---
    pending_users = (
        db.query(User)
        .filter(User.is_active == False, User.role == UserRole.USER)
        .all()
    )
    all_users = db.query(User).filter(User.role == UserRole.USER).all()

    # --- Logs: window + filters ---
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=log_days)

    base_q = (
        db.query(
            UserLog.user_id,
            User.full_name.label("username"),
            UserLog.action,
            UserLog.timestamp,
        )
        .join(User, User.id == UserLog.user_id)
        .filter(UserLog.timestamp >= since, UserLog.timestamp <= now)
    )

    if q:
        like = f"%{q}%"
        base_q = base_q.filter(
            or_(User.full_name.ilike(like), UserLog.action.ilike(like))
        )

    if action_filter:
        base_q = base_q.filter(UserLog.action == action_filter)

    total_count = base_q.with_entities(func.count()).scalar() or 0

    user_logs = (
        base_q.order_by(UserLog.timestamp.desc())
        .offset(log_skip)
        .limit(log_limit)
        .all()
    )

    return templates.TemplateResponse(
        "admindashboard.html",
        {
            "request": request,
            "admin": admin,

            # data for sections
            "pending_users": pending_users,
            "all_users": all_users,

            # logs data
            "user_logs": user_logs,
            "total_count": total_count,
            "log_days": log_days,
            "q": q or "",
            "action_filter": action_filter or "",
            "log_skip": log_skip,
            "log_limit": log_limit,

            # ui state: which tab to open on load
            "active_tab": tab,

            # csv feedback
            "msg": msg,
            "error": error,
            "duplicates": duplicates.split(",") if duplicates else [],
        },
    )

# ------------------------------
# Helpers
# ------------------------------
def _redirect_to_admin_tab(tab: str = "pending") -> RedirectResponse:
    """Redirect back to admin with a specific tab selected."""
    return RedirectResponse(f"/admin?tab={tab}", status_code=303)

# ------------------------------
# Approve user
# ------------------------------
@router.post("/approve/{user_id}")
def approve_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_active = True
        db.commit()
        db.add(UserLog(user_id=user.id, action="APPROVED"))
        db.commit()
    return _redirect_to_admin_tab("pending")

# ------------------------------
# Reject user
# ------------------------------
@router.post("/reject/{user_id}")
def reject_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        db.add(UserLog(user_id=user.id, action="REJECTED"))
        db.commit()
        db.delete(user)
        db.commit()
    return _redirect_to_admin_tab("pending")

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
    return _redirect_to_admin_tab("allusers")

# ------------------------------
# Admin logout
# ------------------------------
@router.get("/logout")
def admin_logout():
    resp = RedirectResponse("/auth/login")
    resp.delete_cookie("user_email")
    return resp

# ------------------------------
# Logs export (CSV)
# ------------------------------
@router.get("/logs-export")
def logs_export(
    db: Session = Depends(get_db),
    log_days: int = Query(2, ge=1, le=30),
    q: str | None = Query(None),
    action_filter: str | None = Query(None),
):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=log_days)

    base_q = (
        db.query(
            UserLog.user_id,
            User.full_name.label("username"),
            UserLog.action,
            UserLog.timestamp,
        )
        .join(User, User.id == UserLog.user_id)
        .filter(UserLog.timestamp >= since, UserLog.timestamp <= now)
    )

    if q:
        like = f"%{q}%"
        base_q = base_q.filter(or_(User.full_name.ilike(like), UserLog.action.ilike(like)))

    if action_filter:
        base_q = base_q.filter(UserLog.action == action_filter)

    rows = base_q.order_by(UserLog.timestamp.desc()).all()

    lines = ["user_id,username,action,timestamp"]
    for r in rows:
        # If values can contain commas, escape/wrap as needed.
        lines.append(f"{r.user_id},{r.username},{r.action},{r.timestamp}")

    csv_text = "\n".join(lines)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=logs.csv"},
    )
