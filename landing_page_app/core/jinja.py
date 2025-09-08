# landing_page_app/core/jinja.py
from fastapi.templating import Jinja2Templates
from fastapi import Request
from landing_page_app.models.user import User, UserRole

# Single, shared Jinja environment for the whole app
templates = Jinja2Templates(directory="landing_page_app/templates")

# ---- Helpers available inside Jinja templates ----
def current_user(request: Request):
    """Return the user object attached by middleware (or None)."""
    return getattr(request.state, "user", None)

def is_admin(user: User | None) -> bool:
    if not user:
        return False
    role = getattr(user, "role", None)
    # Works whether role is an enum or a plain string
    try:
        return role == UserRole.ADMIN
    except Exception:
        return str(role).upper() == "ADMIN"

# Register helpers
templates.env.globals["current_user"] = current_user
templates.env.globals["is_admin"] = is_admin