# landing_page_app/routers/admin.py
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
from pathlib import Path
from passlib.hash import bcrypt
from typing import Optional
import csv, io

from fastapi import APIRouter, Depends, Request, Cookie, Query, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import or_, func, desc
from sqlalchemy.orm import Session

from landing_page_app.database import get_db
from landing_page_app.models.user import User, UserRole
from landing_page_app.models.log import UserLog
from landing_page_app.core.jinja import templates
from landing_page_app.deps import get_current_user
from landing_page_app.models import Candidate

router = APIRouter(tags=["Admin"])


# --------------------------- helpers ---------------------------

def _is_admin(user: User) -> bool:
    role = getattr(user, "role", None)
    try:
        return role == UserRole.ADMIN
    except Exception:
        return str(role).upper() == "ADMIN"


def _require_admin(db: Session, user_email: Optional[str]):
    if not user_email:
        return None, RedirectResponse(url="/login?next=/admin", status_code=302)
    admin = db.query(User).filter(User.email == user_email).first()
    if not admin:
        return None, RedirectResponse(url="/login?next=/admin", status_code=302)
    if not _is_admin(admin):
        return None, RedirectResponse(url="/templates/?error=access_denied", status_code=302)
    return admin, None


# -------------------- background enter (no re-login) --------------------

@router.get("/enter")
def enter_admin(user=Depends(get_current_user)):
    try:
        if _is_admin(user):
            return RedirectResponse(url="/admin", status_code=302)
        return RedirectResponse(url="/templates/?error=access_denied", status_code=302)
    except Exception:
        return RedirectResponse(url="/login?next=/admin", status_code=302)


# ------------------------------ dashboard ------------------------------

@router.get("/", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),

    # CHANGED: make tab optional so we can restore it from cookie if missing
    tab: str | None = Query(None, description="pending|logs|allusers|uploadcsv"),

    # toast / feedback
    msg: str | None = Query(None),
    error: str | None = Query(None),
    duplicates: str | None = Query(None),

    # LOGS (event-by-event) filters + paging
    log_days: int = Query(7, ge=1, le=90),
    q: str | None = Query(None, description="search username or action"),
    action_filter: str | None = Query(None),
    log_skip: int = Query(0, ge=0),
    log_limit: int = Query(20, ge=1, le=200),

    # LOGS SUMMARY (grouped by user) paging
    summary_skip: int = Query(0, ge=0),
    summary_limit: int = Query(20, ge=1, le=200),

    # Which logs view to show by default (persisted via query param)
    logs_view: str = Query("summary"),  # "summary" or "events"

    # ALL USERS search + paging
    users_q: str | None = Query(None),
    users_page: int = Query(1, ge=1),
    users_page_size: int = Query(10, ge=5, le=100),
):
    # Auth
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    allowed_tabs = {"pending", "logs", "allusers", "uploadcsv"}

    # NEW: remember last active tab via cookie if query param is missing
    if not tab:
        tab = request.cookies.get("admin_last_tab", "pending")
    if tab not in allowed_tabs:
        tab = "pending"

    # normalize logs_view
    logs_view = "events" if str(logs_view).lower() == "events" else "summary"

    # ---------- Pending users ----------
    pending_users = db.query(User).filter(User.is_active == False).all()  # noqa: E712

    # ---------- All users (search + pagination) ----------
    users_base = db.query(User)
    if users_q:
        like = f"%{users_q}%"
        users_base = users_base.filter(or_(User.full_name.ilike(like), User.email.ilike(like)))
    users_total = users_base.count()
    users_total_pages = max(1, (users_total + users_page_size - 1) // users_page_size)
    users_page = min(users_page, users_total_pages)
    users_offset = (users_page - 1) * users_page_size
    all_users_page = (
        users_base.order_by(User.created_at.desc())
        .offset(users_offset)
        .limit(users_page_size)
        .all()
    )

    # ---------- Logs date window ----------
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=log_days)

    # ---------- LOGS (event-by-event) ----------
    logs_q = (
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
        logs_q = logs_q.filter(or_(User.full_name.ilike(like), UserLog.action.ilike(like)))
    if action_filter:
        logs_q = logs_q.filter(UserLog.action == action_filter)

    total_count = logs_q.with_entities(func.count()).scalar() or 0
    user_logs = (
        logs_q.order_by(UserLog.timestamp.desc())
        .offset(log_skip)
        .limit(log_limit)
        .all()
    )
    has_prev = log_skip > 0
    has_next = (log_skip + log_limit) < total_count
    prev_skip = max(0, log_skip - log_limit)
    next_skip = log_limit + log_skip
    display_start = 0 if total_count == 0 else (log_skip + 1)
    display_end = total_count if (log_skip + log_limit) > total_count else (log_skip + log_limit)

    # ---------- LOGS SUMMARY (grouped by user) ----------
    count_distinct_q = (
        db.query(func.count(func.distinct(UserLog.user_id)))
        .join(User, User.id == UserLog.user_id)
        .filter(UserLog.timestamp >= since, UserLog.timestamp <= now)
    )
    if q:
        like = f"%{q}%"
        count_distinct_q = count_distinct_q.filter(or_(User.full_name.ilike(like), UserLog.action.ilike(like)))
    if action_filter:
        count_distinct_q = count_distinct_q.filter(UserLog.action == action_filter)
    summary_total_users = count_distinct_q.scalar() or 0

    summary_rows_q = (
        db.query(
            User.id.label("user_id"),
            User.full_name.label("username"),
            func.count(UserLog.id).label("events"),
            func.max(UserLog.timestamp).label("last_ts"),
        )
        .join(UserLog, UserLog.user_id == User.id)
        .filter(UserLog.timestamp >= since, UserLog.timestamp <= now)
    )
    if q:
        like = f"%{q}%"
        summary_rows_q = summary_rows_q.filter(or_(User.full_name.ilike(like), UserLog.action.ilike(like)))
    if action_filter:
        summary_rows_q = summary_rows_q.filter(UserLog.action == action_filter)

    logs_summary = (
        summary_rows_q
        .group_by(User.id, User.full_name)
        .order_by(desc("last_ts"))
        .offset(summary_skip)
        .limit(summary_limit)
        .all()
    )

    # BUILD CONTEXT ONCE, THEN RETURN AND SET COOKIE
    context = {
        "request": request,
        "admin": admin,
        "active_tab": tab,

        "pending_users": pending_users,

        "all_users_page": all_users_page,
        "users_total": users_total,
        "users_page": users_page,
        "users_page_size": users_page_size,
        "users_total_pages": users_total_pages,
        "users_q": users_q or "",

        "user_logs": user_logs,
        "total_count": total_count,
        "log_days": log_days,
        "q": q or "",
        "action_filter": action_filter or "",
        "log_skip": log_skip,
        "log_limit": log_limit,
        "has_prev": has_prev,
        "has_next": has_next,
        "prev_skip": prev_skip,
        "next_skip": next_skip,
        "display_start": display_start,
        "display_end": display_end,

        "logs_summary": logs_summary,
        "summary_total_users": summary_total_users,
        "summary_skip": summary_skip,
        "summary_limit": summary_limit,

        "logs_view": logs_view,

        "msg": msg,
        "error": error,
        "duplicates": duplicates.split(",") if duplicates else [],
    }

    resp = templates.TemplateResponse("admindashboard.html", context)
    # NEW: remember last selected tab for 24 hours
    resp.set_cookie("admin_last_tab", tab, max_age=86400)
    return resp


# ----------------------- admin: view & edit user -----------------------

def _coerce_role(value: str | None) -> UserRole | None:
    if not value:
        return None
    try:
        # value might be "ADMIN" / "USER" / etc.
        normalized = str(value).strip().upper()
        return UserRole[normalized] if hasattr(UserRole, normalized) else None
    except Exception:
        return None


def _build_user_dashboard_context(db: Session, user: User) -> dict:
    """
    Safe defaults so the user dashboard template never crashes.
    If you already have a real context builder for the user dashboard,
    import and call it here instead of this shim.
    """
    return {
        "user": user,
        "kpis": {},
        "clients": [],
        "jobs": [],
        "logs": [],
        "filters": {},
        "admin_preview": True,
    }


@router.get("/users/{user_id}/view", response_class=HTMLResponse)
def admin_view_user(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    # Admin check
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Build context expected by the normal user dashboard
    ctx = _build_user_dashboard_context(db, target)
    ctx["request"] = request
    ctx["admin"] = admin

    # Try likely template names so we don't 500 on filename mismatch
    candidate_templates = [
        "userdashboard.html",
        "user_dashboard.html",
        "dashboard.html",
        "users/dashboard.html",
    ]
    last_err = None
    for tname in candidate_templates:
        try:
            return templates.TemplateResponse(tname, ctx)
        except Exception as e:
            last_err = e
            # Try the next candidate

    # Final safe fallback: render a small HTML so we never 500
    safe_html = f"""
    <!doctype html>
    <html>
      <head><meta charset="utf-8"><title>Admin Preview</title></head>
      <body style="font-family: system-ui, sans-serif; padding:16px">
        <h2>Admin preview of {getattr(target, 'full_name', None) or target.email}</h2>
        <p>Could not find a matching user dashboard template.</p>
        <p>Tried: {', '.join(candidate_templates)}.</p>
        <p><small>{last_err!s}</small></p>
        <p><a href="/admin/?tab=allusers">← Back to All Users</a></p>
      </body>
    </html>
    """
    return HTMLResponse(content=safe_html, status_code=200)


@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
def admin_edit_user_form(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return templates.TemplateResponse(
        "admin_user_edit.html",  # create this template
        {
            "request": request,
            "admin": admin,
            "user": user,
            "roles": [r.name for r in UserRole] if hasattr(UserRole, "__members__") else ["ADMIN", "USER"],
        },
    )


@router.post("/users/{user_id}/edit")
def admin_update_user(
    user_id: int,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),

    full_name: str = Form(...),
    email: str = Form(...),
    is_active: bool = Form(False),
    role: str | None = Form(None),

    # NEW: optional admin-set password fields
    new_password: str | None = Form(None),
    confirm_password: str | None = Form(None),
    force_password_change: str | None = Form(None),  # checkbox => "on" or None
):
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Basic info
    user.full_name = (full_name or "").strip()
    user.email = (email or "").strip()
    user.is_active = bool(is_active)

    # Role
    coerced = _coerce_role(role)
    if coerced is not None:
        user.role = coerced

    # Password change (optional)
    did_change_password = False
    if new_password:
        if not confirm_password or new_password != confirm_password:
            return RedirectResponse(
                url=f"/admin/users/{user_id}/edit?error=Passwords+do+not+match",
                status_code=303,
            )
        # IMPORTANT: adjust the attribute if your model uses a different name
        user.hashed_password = bcrypt.hash(new_password)
        did_change_password = True

    # Optional: mark for forced reset on next login (if your model has the column)
    if hasattr(user, "must_change_password"):
        if force_password_change or did_change_password:
            user.must_change_password = True

    db.add(user)

    # Logging
    if did_change_password:
        db.add(UserLog(user_id=admin.id, action=f"RESET PASSWORD for {user.email}"))
    db.add(UserLog(user_id=admin.id, action=f"EDITED USER {user.email}"))
    db.commit()

    return RedirectResponse(url="/admin?tab=allusers&msg=User%20updated", status_code=302)


# -------------------------- user moderation --------------------------

@router.post("/approve/{user_id}")
def approve_user(user_id: int, db: Session = Depends(get_db), user_email: str | None = Cookie(None)):
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    target = db.get(User, user_id)
    if target:
        target.is_active = True
        db.add(UserLog(user_id=admin.id, action=f"APPROVED {target.email}"))
        db.commit()
    return RedirectResponse(url="/admin?tab=pending&msg=User%20approved", status_code=302)


@router.post("/reject/{user_id}")
def reject_user(user_id: int, db: Session = Depends(get_db), user_email: str | None = Cookie(None)):
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    target = db.get(User, user_id)
    if target:
        db.delete(target)
        db.add(UserLog(user_id=admin.id, action=f"REJECTED {target.email}"))
        db.commit()
    return RedirectResponse(url="/admin?tab=pending&msg=User%20rejected", status_code=302)


@router.post("/remove/{user_id}")
def remove_user(user_id: int, db: Session = Depends(get_db), user_email: str | None = Cookie(None)):
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    target = db.get(User, user_id)
    if target:
        db.delete(target)
        db.add(UserLog(user_id=admin.id, action=f"REMOVED {target.email}"))
        db.commit()
    return RedirectResponse(url="/admin?tab=allusers&msg=User%20removed", status_code=302)


# ------------------------------ CSV upload ------------------------------
@router.post("/upload-csv")
def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    # check admin login
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    # save raw file
    upload_dir = Path("uploaded_csv")
    upload_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = f"{ts}-{file.filename}"
    dest = upload_dir / safe_name
    raw = file.file.read()
    dest.write_bytes(raw)

    # parse CSV and insert unique candidates
    inserted, duplicates = 0, []
    try:
        text = raw.decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))

        for row in reader:
            email = row.get("email")
            name = row.get("candidate_name")
            contact = row.get("contact")

            # uniqueness rule
            if email:
                exists = db.query(Candidate).filter(Candidate.email == email).first()
            else:
                exists = db.query(Candidate).filter(
                    Candidate.candidate_name == name,
                    Candidate.contact == contact
                ).first()

            if exists:
                duplicates.append(email or f"{name}-{contact}")
                continue

            candidate = Candidate(
                candidate_name=name,
                contact=contact,
                email=email,
                location=row.get("location"),
                skillset=row.get("skillset"),
                relevant_experience=row.get("relevant_experience"),
                it_experience=row.get("it_experience"),
                education=row.get("education"),
                company=row.get("company"),
                resumelinks=row.get("resumelinks"),
                comment=row.get("comment"),
                clients=row.get("clients"),
                notice_period=row.get("notice_period"),
                recruitment_notes=row.get("recruitment_notes"),
                ai_score=int(row["ai_score"]) if row.get("ai_score") else None,
                ai_explanation=row.get("ai_explanation"),
            )
            db.add(candidate)
            inserted += 1

        db.add(UserLog(user_id=admin.id, action=f"CSV UPLOAD {file.filename} inserted={inserted}, duplicates={len(duplicates)}"))
        db.commit()

    except Exception as e:
        print("Error processing CSV:", e)
        inserted, duplicates = 0, []

    return RedirectResponse(
        url=f"/admin?tab=uploadcsv&msg=Uploaded%20{quote_plus(file.filename)}%20({inserted}%20rows)&duplicates={','.join(duplicates)}",
        status_code=302,
    )


# ------------------------ Logs export (CSV) ------------------------

@router.get("/logs-export")
def logs_export(db: Session = Depends(get_db), user_email: str | None = Cookie(None)):
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=30)
    rows = (
        db.query(UserLog.user_id, User.full_name.label("username"), UserLog.action, UserLog.timestamp)
        .join(User, User.id == UserLog.user_id)
        .filter(UserLog.timestamp >= since, UserLog.timestamp <= now)
        .order_by(UserLog.timestamp.desc())
        .all()
    )
    lines = ["user_id,username,action,timestamp"]
    for r in rows:
        lines.append(f"{r.user_id},{quote_plus(r.username)},{quote_plus(r.action)},{r.timestamp.isoformat()}")
    csv_text = "\n".join(lines)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=logs.csv"},
    )


# --------------------- JSON: logs for a single user ---------------------

@router.get("/logs/user/{user_id}.json")
def logs_for_user_json(
    user_id: int,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
    days: int = Query(7, ge=1, le=90),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=300),
):
    _, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    base = (
        db.query(UserLog.action, UserLog.timestamp)
        .filter(
            UserLog.user_id == user_id,
            UserLog.timestamp >= since,
            UserLog.timestamp <= now,
        )
    )
    total = base.with_entities(func.count()).scalar() or 0
    rows = base.order_by(UserLog.timestamp.desc()).offset(skip).limit(limit).all()

    user = db.get(User, user_id)
    return {
        "user_id": user_id,
        "username": getattr(user, "full_name", "") if user else "",
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [
            {"action": r.action, "timestamp": r.timestamp.isoformat()}
            for r in rows
        ],
    }
