# landing_page_app/routers/user_activity.py
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

# Primary known imports (most likely in your project)
try:
    from landing_page_app.database import get_db
except Exception:
    # fallback if your DB helper file is named differently
    try:
        from landing_page_app.db import get_db
    except Exception:
        from landing_page_app.db_session import get_db  # last-resort common name

# Import models (these paths are consistent with your snippets)
from landing_page_app.models.user import User
from landing_page_app.models.log import UserLog

# Try to import your app's get_current_user from a few likely places
get_current_user = None
_try_paths = [
    "landing_page_app.dependencies",
    "landing_page_app.routers.utils.dependencies",
    "landing_page_app.routers.utils.auth_dependencies",
    "landing_page_app.auth.dependencies",
    "landing_page_app.routers.auth.dependencies",
]
for p in _try_paths:
    try:
        mod = __import__(p, fromlist=["get_current_user"])
        get_current_user = getattr(mod, "get_current_user")
        break
    except Exception:
        get_current_user = None

if get_current_user is None:
    # Final fallback: attempt to import a function named 'get_current_user' from 'landing_page_app.routers.auth'
    try:
        mod = __import__("landing_page_app.routers.auth", fromlist=["get_current_user"])
        get_current_user = getattr(mod, "get_current_user", None)
    except Exception:
        get_current_user = None

# Load the same Jinja2Templates you already use in pages.py if available,
# otherwise create a local templates loader pointed at the same directory.
try:
    # pages.py defines `templates = Jinja2Templates(directory="landing_page_app/templates")`
    from landing_page_app.routers.pages import templates
except Exception:
    try:
        from landing_page_app.pages import templates
    except Exception:
        # fallback: create our own loader (safe)
        from fastapi.templating import Jinja2Templates
        templates = Jinja2Templates(directory="landing_page_app/templates")


router = APIRouter(tags=["User Activity"])


@router.get("/user/{user_id}/activity", response_class=HTMLResponse)
def user_activity_page(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(lambda: None) if get_current_user is None else Depends(get_current_user),
    days: int = Query(15, ge=1, le=90, description="Days back to show"),
    skip: int = Query(0, ge=0, description="Number of items to skip (pagination)"),
    limit: int = Query(50, ge=1, le=300, description="Max items per page"),
):
    """
    Render the activity page for the logged-in user.
    - Only the same user (current_user.id == user_id) can view this page.
    - Shows actions from UserLog for the last `days` days (default 15).
    - Pagination: skip / limit.
    """

    # If we couldn't import any get_current_user, treat as not-logged-in and redirect to login.
    if current_user is None:
        return RedirectResponse(url=f"/login?next=/user/{user_id}/activity", status_code=302)

    # Ensure only the same user can view
    try:
        if int(current_user.id) != int(user_id):
            return RedirectResponse(url="/templates?error=access_denied", status_code=302)
    except Exception:
        return RedirectResponse(url="/templates?error=access_denied", status_code=302)

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    base_q = (
        db.query(UserLog.action, UserLog.timestamp)
        .filter(
            UserLog.user_id == user_id,
            UserLog.timestamp >= since,
            UserLog.timestamp <= now,
        )
    )
    total = base_q.with_entities(func.count()).scalar() or 0
    rows = base_q.order_by(UserLog.timestamp.desc()).offset(skip).limit(limit).all()

    context = {
        "request": request,
        "user": current_user,
        "user_id": user_id,
        "username": getattr(current_user, "full_name", getattr(current_user, "name", "")),
        "items": rows,
        "total": total,
        "skip": skip,
        "limit": limit,
        "days": days,
    }

    return templates.TemplateResponse("user_activity.html", context)
