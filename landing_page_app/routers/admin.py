# admin.py (updated: added route admin_user_logs_page)
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

from landing_page_app.database import get_db
from landing_page_app.models.user import User, UserRole
from landing_page_app.models.log import UserLog
from landing_page_app.core.jinja import templates
from landing_page_app.deps import get_current_user
from landing_page_app.models import Candidate
from landing_page_app.services.embedding_service import embed_text

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

    # raw grouped rows (same as before)
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

    raw_summary_rows = (
        summary_rows_q
        .group_by(User.id, User.full_name)
        .order_by(desc("last_ts"))
        .offset(summary_skip)
        .limit(summary_limit)
        .all()
    )

    # Build a processed list that includes the login status for each user.
    # Determine status by looking up the latest UserLog.action (no date window) for that user.
    # Mapping rule:
    #  - latest action starting with "LOGIN" (case-insensitive) => Active
    #  - latest action starting with "LOGOUT" => Inactive
    #  - otherwise fallback: if "LOGIN" appears anywhere => Active, else Inactive
    processed_logs_summary = []
    for r in raw_summary_rows:
        status = "Inactive"  # default

# Find the most recent UserLog for this user (no date window)
        latest = (
            db.query(UserLog.action, UserLog.timestamp)
            .filter(UserLog.user_id == r.user_id)
            .order_by(UserLog.timestamp.desc())
            .limit(1)
            .first()
        )

        if latest:
            action_text = (latest.action or "").strip().upper()
            # ✅ Detect "LOGIN" even if it's embedded (e.g., "USER LOGIN SUCCESS")
            if "LOGIN" in action_text and not "LOGOUT" in action_text:
                status = "Active"
            elif "LOGOUT" in action_text:
                status = "Inactive"
            else:
                # Optional fallback: if last log was within last 10 minutes, treat as active
                now = datetime.now(timezone.utc)
                if (now - latest.timestamp) < timedelta(minutes=10):
                    status = "Active"


        processed_logs_summary.append({
            "user_id": r.user_id,
            "username": r.username,
            "events": r.events,
            "last_ts": r.last_ts,
            "status": status,
        })

    # expose processed list to the template (keeps the same variable name)
    logs_summary = processed_logs_summary


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

    # remember old role for comparison
    old_role = getattr(user, "role", None)

    # Basic info
    user.full_name = (full_name or "").strip()
    user.email = (email or "").strip()
    user.is_active = bool(is_active)

    # Role
    coerced = _coerce_role(role)
    role_changed = False
    if coerced is not None and coerced != old_role:
        user.role = coerced
        role_changed = True

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

    # Build a friendly msg parameter depending on what changed
    msgs = []
    if did_change_password:
        msgs.append("Password updated successfully")
    if role_changed:
        # role is an enum; convert to displayable string
        try:
            role_display = user.role.name if hasattr(user.role, "name") else str(user.role)
        except Exception:
            role_display = str(user.role)
        msgs.append(f"Role updated to {role_display} successfully")

    # Fallback generic message if nothing specific
    if not msgs:
        msgs.append("User updated")

    combined_msg = "; ".join(msgs)
    return RedirectResponse(url=f"/admin?tab=allusers&msg={quote_plus(combined_msg)}", status_code=302)


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
    if not target:
        return RedirectResponse(url="/admin?tab=allusers&error=User%20not%20found", status_code=302)

    try:
        # 🧩 Directly delete the user and log the admin action.
        db.delete(target)
        db.add(UserLog(user_id=admin.id, action=f"REMOVED {target.email}"))

        db.commit()

        return RedirectResponse(url="/admin?tab=allusers&msg=User%20removed", status_code=302)

    except IntegrityError:
        db.rollback()
        import logging
        logging.exception("Foreign key constraint failed while deleting user %s", user_id)
        return RedirectResponse(
            url="/admin?tab=allusers&error=Cannot%20remove%20user%20-%20references%20exist",
            status_code=303,
        )

    except Exception:
        db.rollback()
        import logging
        logging.exception("Unexpected error deleting user %s", user_id)
        return RedirectResponse(
            url="/admin?tab=allusers&error=Failed%20to%20remove%20user",
            status_code=303,
        )



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

    try:
        raw = file.file.read()
        dest.write_bytes(raw)

        # try a couple of decodings (utf-8 fallback to latin-1)
        text = None
        try:
            text = raw.decode("utf-8")
        except Exception:
            try:
                text = raw.decode("latin-1")
            except Exception:
                text = raw.decode("utf-8", errors="ignore")

        # helper: normalize header keys to lowercase trimmed values
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV file has no header row or unreadable header")

        # normalize fieldnames map: maps lowercase stripped header -> original header
        normalized_field_map = {fn.strip().lower(): fn for fn in (reader.fieldnames or [])}

        def get_field(row, *possible_names):
            """Return stripped string value for the first matching header in possible_names (case-insensitive)."""
            for nm in possible_names:
                key = nm.strip().lower()
                if key in normalized_field_map:
                    val = row.get(normalized_field_map[key], "")
                    return (val or "").strip()
            return ""

        def safe_int(val):
            if val is None:
                return None
            s = str(val).strip()
            if s == "":
                return None
            # remove commas and whitespace
            s = s.replace(",", "")
            try:
                return int(float(s))
            except Exception:
                return None

        inserted = 0
        duplicates = []

        for row in reader:
            # read common fields using flexible header names
            email = get_field(row, "email", "e-mail")
            name = get_field(row, "candidate_name", "name", "full_name")
            contact = get_field(row, "contact", "phone", "phone_number", "mobile")
            location = get_field(row, "location")
            skillset = get_field(row, "skillset", "skills")
            relevant_experience = get_field(row, "relevant_experience", "experience", "relevantexp")
            it_experience = get_field(row, "it_experience", "it_experience_years", "it_experience_years")
            education = get_field(row, "education")
            company = get_field(row, "company", "current_company")
            resumelinks = get_field(row, "resumelinks", "resume_link", "resume")
            comment = get_field(row, "comment", "notes")
            clients_field = get_field(row, "clients")
            notice_period = get_field(row, "notice_period", "notice")
            recruitment_notes = get_field(row, "recruitment_notes", "recruiter_notes", "recruitment_notes")
            ai_score = safe_int(get_field(row, "ai_score", "ai score", "ai_score"))
            ai_explanation = get_field(row, "ai_explanation", "ai explanation")

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
            
            
            # ------------------ BUILD EMBEDDING TEXT ------------------
            embed_parts = []

            if skillset:
                embed_parts.append(f"Skills: {skillset}")

            if it_experience:
                embed_parts.append(f"IT Experience: {it_experience}")

            if relevant_experience:
                embed_parts.append(f"Relevant Experience: {relevant_experience}")

            if location:
                embed_parts.append(f"Location: {location}")

            embedding_text = " | ".join(embed_parts).strip()

            embedding_vector = None
            if embedding_text:
                try:
                    embedding_vector = embed_text(embedding_text)
                except Exception as e:
                    # Do NOT break CSV upload for embedding issues
                    print(f"[EMBEDDING ERROR] {email or name}: {e}")
                    embedding_vector = None


            candidate = Candidate(
                candidate_name=name,
                contact=contact,
                email=email,
                location=location,
                skillset=skillset,
                relevant_experience=relevant_experience,
                it_experience=it_experience,
                education=education,
                company=company,
                resumelinks=resumelinks,
                comment=comment,
                clients=clients_field,
                notice_period=notice_period,
                recruitment_notes=recruitment_notes,
                ai_score=ai_score,
                ai_explanation=ai_explanation,
                embedding=embedding_vector,
            )
            db.add(candidate)
            inserted += 1

        # Commit once after processing all rows
        db.add(UserLog(user_id=admin.id, action=f"CSV UPLOAD {file.filename} inserted={inserted}, duplicates={len(duplicates)}"))
        db.commit()

    except Exception as e:
        # Log to console for debugging and return to UI with error visible
        print("Error processing CSV:", repr(e))
        try:
            # attempt to rollback any partial transaction
            db.rollback()
        except Exception:
            pass

        # Redirect back and show the error (URL-encoded)
        return RedirectResponse(
            url=f"/admin?tab=uploadcsv&error=CSV+upload+failed:+{quote_plus(str(e))}",
            status_code=302,
        )

    # Success redirect (duplicates list optional)
    dup_param = ",".join(duplicates) if duplicates else ""
    return RedirectResponse(
        url=f"/admin?tab=uploadcsv&msg=Uploaded%20{quote_plus(file.filename)}%20({inserted}%20rows)&duplicates={quote_plus(dup_param)}",
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

# --------------------- NEW: HTML page for logs of single user ---------------------
@router.get("/logs/user/{user_id}", response_class=HTMLResponse)
def admin_user_logs_page(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
    days: int = Query(7, ge=1, le=90),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=300),
):
    admin, redirect = _require_admin(db, user_email)
    if redirect:
        return redirect

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    rows = (
        db.query(UserLog.action, UserLog.timestamp)
        .filter(
            UserLog.user_id == user_id,
            UserLog.timestamp >= since,
            UserLog.timestamp <= now,
        )
        .order_by(UserLog.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ✅ Friendly LINK/UNLINK Activity Formatter
    from landing_page_app.models.candidates import Candidate
    from landing_page_app.models.jobs import Job
    from landing_page_app.models.clients import Client

    processed_items = []
    for r in rows:
        text = r.action

        # ✅ LINKED example:
        # "LINKED CANDIDATE ID:714 to JOB 20"
        if text.startswith("LINKED CANDIDATE"):
            parts = text.split()
            cand_id = int(parts[2].replace("ID:", ""))
            job_id = int(parts[-1])

            cand = db.get(Candidate, cand_id)
            job = db.get(Job, job_id)
            client = db.get(Client, job.client_id) if job else None

            if cand and job:
                text = (
                    f"LINKED {cand.candidate_name} → {job.job_title}"
                    f" @ {client.client_name if client else 'N/A'}"
                )

        # ✅ UNLINKED example:
        # "UNLINKED CANDIDATE ID:714 from JOB 20"
        if text.startswith("UNLINKED CANDIDATE"):
            parts = text.split()
            cand_id = int(parts[2].replace("ID:", ""))
            job_id = int(parts[-1])

            cand = db.get(Candidate, cand_id)
            job = db.get(Job, job_id)
            client = db.get(Client, job.client_id) if job else None

            if cand and job:
                text = (
                    f"UNLINKED {cand.candidate_name} ✕ {job.job_title}"
                    f" @ {client.client_name if client else 'N/A'}"
                )

        processed_items.append({"action": text, "timestamp": r.timestamp})

    ctx = {
        "request": request,
        "admin": admin,
        "target_user": user,
        "days": days,
        "skip": skip,
        "limit": limit,
        "total": len(processed_items),
        "items": processed_items,
    }

    return templates.TemplateResponse("admin_user_logs.html", ctx)


# --------------------- NEW: HTML page for logs of single user ---------------------
@router.get("/logs/user/{user_id}", response_class=HTMLResponse)
def admin_user_logs_page(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
    days: int = Query(7, ge=1, le=90),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=300),
):
    """
    Render a dedicated page showing the logs for a single user.
    This uses the same filters/paging as the JSON endpoint but returns a template.
    """
    admin, redirect = _require_admin(db, user_email)
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
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    ctx = {
        "request": request,
        "admin": admin,
        "target_user": user,
        "days": days,
        "skip": skip,
        "limit": limit,
        "total": total,
        "items": [{"action": r.action, "timestamp": r.timestamp} for r in rows],
    }

    # Render a simple template (see admin_user_logs.html below)
    return templates.TemplateResponse("admin_user_logs.html", ctx)
