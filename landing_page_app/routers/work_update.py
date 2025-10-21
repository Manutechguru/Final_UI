# landing_page_app/routers/work_update.py
import os
import json
import base64
from urllib.parse import urlencode
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, status, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

# Attempt to import project's get_db / templates / get_current_user in same manner as user_activity.py
try:
    from landing_page_app.database import get_db
except Exception:
    try:
        from landing_page_app.db import get_db
    except Exception:
        from landing_page_app.db_session import get_db

# templates object reuse (falls back if not available)
try:
    from landing_page_app.routers.pages import templates
except Exception:
    try:
        from landing_page_app.pages import templates
    except Exception:
        from fastapi.templating import Jinja2Templates
        templates = Jinja2Templates(directory="landing_page_app/templates")

# attempt to import get_current_user similar to user_activity.py
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
    try:
        mod = __import__("landing_page_app.routers.auth", fromlist=["get_current_user"])
        get_current_user = getattr(mod, "get_current_user", None)
    except Exception:
        get_current_user = None

router = APIRouter(tags=["Work Update"])

# -------------------------
# Minimal DB model for storing Google OAuth tokens
# -------------------------
from sqlalchemy import Column, Integer, Text, DateTime, func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class GoogleOAuthToken(Base):
    __tablename__ = "google_oauth_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False, unique=True)
    token_json = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

def ensure_token_table(engine):
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        # Be defensive: if engine/metadata differs, ignore to avoid breaking app
        pass

# -------------------------
# Helper functions for token checks
# -------------------------
def get_user_token_row(db: Session, user_id: int) -> Optional[GoogleOAuthToken]:
    try:
        return db.query(GoogleOAuthToken).filter(GoogleOAuthToken.user_id == int(user_id)).first()
    except Exception:
        return None

def check_user_token_in_db(db: Session, user_id: int) -> bool:
    if not user_id:
        return False
    row = get_user_token_row(db, user_id)
    return bool(row)

# -------------------------
# SMTP fallback (unchanged)
# -------------------------
def send_email_smtp(from_addr: str, to_addrs: str, subject: str, body: str):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")

    if not smtp_user or not smtp_pass:
        raise RuntimeError("SMTP_USERNAME and SMTP_PASSWORD environment variables must be set for SMTP sending.")

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = to_addrs
    msg["Subject"] = subject or "(No subject)"
    msg.attach(MIMEText(body or "", "html"))

    server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
    server.ehlo()
    if smtp_port == 587:
        server.starttls()
        server.ehlo()
    server.login(smtp_user, smtp_pass)
    server.sendmail(from_addr, [a.strip() for a in to_addrs.split(",")], msg.as_string())
    server.quit()

# -------------------------
# Gmail API sending (using stored OAuth tokens)
# -------------------------
def send_via_gmail_api(db: Session, user_id: int, from_addr: str, to_addrs: str, subject: str, body: str):
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from email.mime.text import MIMEText
    except Exception as e:
        raise RuntimeError("Missing Google API libraries. Install google-auth, google-api-python-client.") from e

    token_row = get_user_token_row(db, user_id)
    if not token_row:
        raise RuntimeError("No Google OAuth token found for user; user must authorize Gmail access.")

    token_data = json.loads(token_row.token_json)

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri"),
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        scopes=token_data.get("scopes", ["https://www.googleapis.com/auth/gmail.send"])
    )

    # Attempt refresh if invalid
    try:
        if not creds.valid and creds.refresh_token:
            try:
                from google.auth.transport.requests import Request as GARequest
                request_adapter = GARequest()
            except Exception:
                request_adapter = None

            if request_adapter is None:
                raise RuntimeError("Cannot refresh credentials: install google-auth[requests].")

            creds.refresh(request_adapter)

            # persist refreshed token
            token_data.update({
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": getattr(creds, "token_uri", token_data.get("token_uri")),
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(creds.scopes) if creds.scopes else [ "https://www.googleapis.com/auth/gmail.send" ]
            })
            token_row.token_json = json.dumps(token_data)
            db.add(token_row)
            db.commit()
    except Exception as exc:
        raise RuntimeError(f"Failed to refresh Google credentials: {exc}") from exc

    # build message and send
    mime_msg = MIMEText(body or "", "html")
    mime_msg["to"] = to_addrs
    mime_msg["subject"] = subject or ""
    mime_msg["from"] = from_addr
    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()

    try:
        service = build("gmail", "v1", credentials=creds)
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return sent
    except Exception as exc:
        raise RuntimeError(f"Gmail API send error: {exc}") from exc

# -------------------------
# OAuth configuration (from env)
# -------------------------
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
GOOGLE_OAUTH_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GOOGLE_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"

def _ensure_db_tables(db: Session):
    try:
        engine = getattr(db, "get_bind", None)
        if callable(engine):
            engine = db.get_bind()
        if engine is None and hasattr(db, "bind"):
            engine = db.bind
        if engine is not None:
            ensure_token_table(engine)
    except Exception:
        # Best-effort: do not raise here
        pass

# -------------------------
# Routes
# -------------------------
@router.get("/work-update/authorize")
def work_update_authorize(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(lambda: None) if get_current_user is None else Depends(get_current_user),
):
    """
    Start OAuth authorization flow. If user not logged-in, redirect to login first.
    """
    if current_user is None:
        # send to login and preserve return-to authorize url
        return RedirectResponse(url="/login?next=/work-update/authorize", status_code=302)

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_REDIRECT_URI:
        return templates.TemplateResponse("base.html", {
            "request": request,
            "user": current_user,
            "from_email": getattr(current_user, "email", ""),
            "manager_email": getattr(current_user, "manager_email", "") or os.getenv("DEFAULT_MANAGER_EMAIL", ""),
            "error": "Gmail OAuth is not configured on the server. Contact admin."
        }, status_code=500)

    _ensure_db_tables(db)

    state = json.dumps({"uid": getattr(current_user, "id", None)})

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "response_type": "code",
        "scope": GOOGLE_OAUTH_SCOPE,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "access_type": "offline",
        "prompt": "consent",
        "state": state
    }
    auth_url = f"{GOOGLE_AUTH_BASE}?{urlencode(params)}"

    # --- DEBUG: print redirect_uri and full auth_url to server logs so you can verify exact values ---
    try:
        print(f"[work_update] redirect_uri -> {GOOGLE_REDIRECT_URI}")
        print(f"[work_update] auth_url -> {auth_url}")
    except Exception:
        pass
    # -----------------------------------------------------------------------------------------------

    return RedirectResponse(url=auth_url)

@router.get("/work-update/oauth2callback")
def work_update_oauth2callback(request: Request, db: Session = Depends(get_db)):
    """
    Callback to exchange code for tokens and save to DB associated with user id from state.
    If state did not contain uid, attempt to resolve current logged-in user from request/state/cookies (best-effort).
    """
    code = request.query_params.get("code")
    state_raw = request.query_params.get("state")
    error = request.query_params.get("error")
    if error:
        return templates.TemplateResponse("base.html", {
            "request": request,
            "error": f"Google Authorization failed: {error}",
            "user": None,
            "from_email": "",
            "manager_email": os.getenv("DEFAULT_MANAGER_EMAIL", "")
        }, status_code=400)

    if not code:
        return templates.TemplateResponse("base.html", {
            "request": request,
            "error": "Missing authorization code from Google.",
            "user": None,
            "from_email": "",
            "manager_email": os.getenv("DEFAULT_MANAGER_EMAIL", "")
        }, status_code=400)

    # parse state for user id
    try:
        state = json.loads(state_raw) if state_raw else {}
        user_id = state.get("uid")
    except Exception:
        user_id = None

    # If state didn't produce user_id, attempt to find current logged-in user (best-effort).
    if not user_id:
        try:
            # many apps set request.state.user in middleware (your main.py does this)
            user_obj = getattr(request.state, "user", None)
            if user_obj and getattr(user_obj, "id", None):
                user_id = getattr(user_obj, "id")
        except Exception:
            user_id = None

    # also attempt cookie-based fallback (if middleware didn't run)
    if not user_id:
        try:
            user_email = request.cookies.get("user_email")
            if user_email:
                # try to resolve via DB
                gen = get_db()
                db = next(gen)
                try:
                    # import here to avoid circular import if User model lives elsewhere
                    try:
                        from landing_page_app.models.user import User
                    except Exception:
                        User = None
                    if User is not None:
                        user_obj = db.query(User).filter(User.email == user_email).first()
                        if user_obj and getattr(user_obj, "id", None):
                            user_id = getattr(user_obj, "id")
                finally:
                    try:
                        gen.close()
                    except Exception:
                        pass
        except Exception:
            pass

    import requests
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    try:
        resp = requests.post(GOOGLE_TOKEN_URI, data=data, timeout=15)
        token_resp = resp.json()
    except Exception as exc:
        return templates.TemplateResponse("base.html", {
            "request": request,
            "error": f"Failed to fetch tokens from Google: {exc}",
            "user": None,
            "from_email": "",
            "manager_email": os.getenv("DEFAULT_MANAGER_EMAIL", "")
        }, status_code=500)

    if "error" in token_resp:
        return templates.TemplateResponse("base.html", {
            "request": request,
            "error": f"Token error: {token_resp.get('error_description') or token_resp.get('error')}",
            "user": None,
            "from_email": "",
            "manager_email": os.getenv("DEFAULT_MANAGER_EMAIL", "")
        }, status_code=400)

    try:
        _ensure_db_tables(db)
        if not user_id:
            # No user id in state and we couldn't deduce it — instruct user to login first.
            return templates.TemplateResponse("base.html", {
                "request": request,
                "error": "Authorized with Google but could not associate token with your user account (no user id found). Please login to the app and try Authorize again.",
                "user": None,
                "from_email": "",
                "manager_email": os.getenv("DEFAULT_MANAGER_EMAIL", "")
            }, status_code=500)

        token_json = json.dumps({
            "token": token_resp.get("access_token"),
            "refresh_token": token_resp.get("refresh_token"),
            "token_uri": GOOGLE_TOKEN_URI,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "scopes": [GOOGLE_OAUTH_SCOPE]
        })

        token_obj = db.query(GoogleOAuthToken).filter(GoogleOAuthToken.user_id == int(user_id)).first()
        if token_obj:
            token_obj.token_json = token_json
        else:
            token_obj = GoogleOAuthToken(user_id=int(user_id), token_json=token_json)
        db.add(token_obj)
        db.commit()

    except Exception as exc:
        return templates.TemplateResponse("base.html", {
            "request": request,
            "error": f"Failed to store Google tokens: {exc}",
            "user": None,
            "from_email": "",
            "manager_email": os.getenv("DEFAULT_MANAGER_EMAIL", "")
        }, status_code=500)

    return RedirectResponse(url="/work-update", status_code=302)

# -------------------------
# Main compose & send routes (kept behavior)
# -------------------------
@router.get("/work-update", response_class=HTMLResponse)
def work_update_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(lambda: None) if get_current_user is None else Depends(get_current_user),
):
    """
    Render the 'compose' page. Prefills the From with current_user.email if available.
    Also provides has_google_token boolean into the template.
    """
    if current_user is None:
        return RedirectResponse(url="/login?next=/work-update", status_code=302)

    _ensure_db_tables(db)

    manager_email = getattr(current_user, "manager_email", None) or os.getenv("DEFAULT_MANAGER_EMAIL", "")

    has_google_token = False
    try:
        has_google_token = check_user_token_in_db(db, getattr(current_user, "id", None))
    except Exception:
        has_google_token = False

    context = {
        "request": request,
        "user": current_user,
        "from_email": getattr(current_user, "email", ""),
        "manager_email": manager_email,
        "has_google_token": has_google_token,
    }
    return templates.TemplateResponse("base.html", context)


@router.post("/work-update/send")
def work_update_send(
    request: Request,
    from_email: str = Form(...),
    to_email: str = Form(...),
    subject: str = Form(""),
    body: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(lambda: None) if get_current_user is None else Depends(get_current_user),
):
    """
    Send the work update email. Uses Gmail API (OAuth) if token present for user;
    otherwise fallback to SMTP or instruct user to authorize.
    """
    if current_user is None:
        return RedirectResponse(url="/login?next=/work-update", status_code=302)

    user_email = getattr(current_user, "email", None)
    if user_email and from_email.strip().lower() != user_email.strip().lower():
        from_email = user_email

    if not to_email:
        raise HTTPException(status_code=400, detail="Recipient (to) is required.")

    user_id = getattr(current_user, "id", None)

    try:
        token_row = get_user_token_row(db, user_id) if user_id else None

        if token_row:
            try:
                send_via_gmail_api(db=db, user_id=int(user_id), from_addr=from_email, to_addrs=to_email, subject=subject, body=body)
                return RedirectResponse(url="/templates?msg=work_update_sent", status_code=status.HTTP_302_FOUND)
            except Exception as exc:
                return templates.TemplateResponse("base.html", {
                    "request": request,
                    "user": current_user,
                    "from_email": from_email,
                    "manager_email": to_email,
                    "error": str(exc),
                    "subject": subject,
                    "body": body
                }, status_code=500)

        smtp_user = os.getenv("SMTP_USERNAME")
        smtp_pass = os.getenv("SMTP_PASSWORD")
        if smtp_user and smtp_pass:
            try:
                send_email_smtp(from_email, to_email, subject, body)
                return RedirectResponse(url="/templates?msg=work_update_sent", status_code=status.HTTP_302_FOUND)
            except Exception as exc:
                return templates.TemplateResponse("base.html", {
                    "request": request,
                    "user": current_user,
                    "from_email": from_email,
                    "manager_email": to_email,
                    "error": str(exc),
                    "subject": subject,
                    "body": body
                }, status_code=500)

        # No SMTP configured and no Google token: instruct user to authorize
        return templates.TemplateResponse("base.html", {
            "request": request,
            "user": current_user,
            "from_email": from_email,
            "manager_email": to_email,
            "error": "Your account is not configured to send mail yet. Click 'Authorize' to connect your Google account (or contact admin).",
            "subject": subject,
            "body": body,
            "show_authorize_hint": True
        }, status_code=400)

    except Exception as exc:
        return templates.TemplateResponse("base.html", {
            "request": request,
            "user": current_user,
            "from_email": from_email,
            "manager_email": to_email,
            "error": str(exc),
            "subject": subject,
            "body": body
        }, status_code=500)
