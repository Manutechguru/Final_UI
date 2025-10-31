# landing_page_app/routers/work_update.py
"""
Work Update router (Gmail send) — updated to store OAuth tokens in a
separate table named `workup_google_oauth_tokens`.

Drop-in replacement for your existing work_update.py.
Keep same endpoints/templates/logic — only token storage and refresh handling changed.
Make sure to set env vars:
  WORKUPD_GOOGLE_CLIENT_ID
  WORKUPD_GOOGLE_CLIENT_SECRET
  WORKUPD_GOOGLE_REDIRECT_URI
(optional) WORKUPD_GOOGLE_TOKEN_URI
"""
import os
import json
import base64
from urllib.parse import urlencode
from typing import Optional, List

from fastapi import APIRouter, Request, Depends, Form, status, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

# Signing utility
try:
    from itsdangerous import URLSafeSerializer, BadSignature
except Exception:
    URLSafeSerializer = None
    BadSignature = Exception

# Try to import project's DB / templates / get_current_user (compatible with your codebase)
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

# attempt to import get_current_user in multiple likely places
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
# Minimal DB model for storing Google OAuth tokens (separate table)
# -------------------------
from sqlalchemy import Column, Integer, Text, DateTime, func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class WorkupGoogleOAuthToken(Base):
    """
    Table name intentionally set to 'workup_google_oauth_tokens' (snake_case)
    so it does not conflict with any other token storage in your app.
    """
    __tablename__ = "workup_google_oauth_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False, unique=True)
    token_json = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

def ensure_token_table(engine):
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass

# -------------------------
# Helper functions for token checks
# -------------------------
def get_user_token_row(db: Session, user_id: int) -> Optional[WorkupGoogleOAuthToken]:
    try:
        return db.query(WorkupGoogleOAuthToken).filter(WorkupGoogleOAuthToken.user_id == int(user_id)).first()
    except Exception:
        return None

def check_user_token_in_db(db: Session, user_id: int) -> bool:
    if not user_id:
        return False
    row = get_user_token_row(db, user_id)
    return bool(row)

# -------------------------
# SMTP fallback, Gmail API send, etc.
# -------------------------
def send_email_smtp(from_addr: str, to_addrs: str, subject: str, body: str,
                    cc_addrs: Optional[str] = None, bcc_addrs: Optional[str] = None,
                    attachments: Optional[List[UploadFile]] = None):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")

    if not smtp_user or not smtp_pass:
        raise RuntimeError("SMTP_USERNAME and SMTP_PASSWORD environment variables must be set for SMTP sending.")

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = to_addrs
    if cc_addrs:
        msg["Cc"] = cc_addrs
    if bcc_addrs:
        msg["Bcc"] = bcc_addrs
    msg["Subject"] = subject or "(No subject)"
    msg["Reply-To"] = from_addr
    msg["MIME-Version"] = "1.0"
    msg["X-Mailer"] = "Teetli WorkUpdateApp"
    msg["X-Priority"] = "1"

    msg.attach(MIMEText(body or "", "html", _charset="utf-8"))

    if attachments:
        for up in attachments:
            try:
                filename = getattr(up, "filename", None) or "attachment"
                content = None
                try:
                    content = up.file.read()
                    try:
                        up.file.seek(0)
                    except Exception:
                        pass
                except Exception:
                    if isinstance(up, (bytes, bytearray)):
                        content = bytes(up)
                    else:
                        content = None
                if content is None:
                    continue

                part = MIMEBase("application", "octet-stream")
                part.set_payload(content)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                msg.attach(part)
            except Exception:
                continue

    recipients = []
    def add_list_from_string(s):
        if not s:
            return
        for a in [x.strip() for x in s.replace(";",",").split(",")]:
            if a:
                recipients.append(a)
    add_list_from_string(to_addrs)
    add_list_from_string(cc_addrs)
    add_list_from_string(bcc_addrs)

    if not recipients:
        raise RuntimeError("No recipients to send to.")
    
    server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
    server.ehlo()
    if smtp_port == 587:
        server.starttls()
        server.ehlo()
    server.login(smtp_user, smtp_pass)
    server.sendmail(from_addr, recipients, msg.as_string())
    server.quit()

def send_via_gmail_api(db: Session, user_id: int, from_addr: str, to_addrs: str, subject: str, body: str,
                       cc_addrs: Optional[str] = None, bcc_addrs: Optional[str] = None,
                       attachments: Optional[List[UploadFile]] = None):
    """
    Send via Gmail API using stored token row for user_id in workup_google_oauth_tokens.
    Robust refresh handling and explicit errors for revoked/expired tokens.
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from email.mime.base import MIMEBase
        from email import encoders
        from email.utils import formatdate, make_msgid as _make_msgid
    except Exception as e:
        raise RuntimeError("Missing Google API libraries. Install google-auth, google-api-python-client.") from e

    token_row = get_user_token_row(db, user_id)
    if not token_row:
        raise RuntimeError("No Google OAuth token found for user; user must authorize Gmail access (Work-Update).")

    # defensive parse
    try:
        token_data = json.loads(token_row.token_json)
    except Exception:
        raise RuntimeError("Stored Google token is corrupt for user. Re-authorize your Google account for Work-Update.")

    # Build credentials object using WORKUPD env based client information
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri") or os.getenv("WORKUPD_GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id") or os.getenv("WORKUPD_GOOGLE_CLIENT_ID"),
        client_secret=token_data.get("client_secret") or os.getenv("WORKUPD_GOOGLE_CLIENT_SECRET"),
        scopes=token_data.get("scopes", ["https://www.googleapis.com/auth/gmail.send"])
    )

    # Attempt refresh before sending; persist new tokens if refreshed
    try:
        if not creds.valid and creds.refresh_token:
            try:
                from google.auth.transport.requests import Request as GARequest
                request_adapter = GARequest()
            except Exception:
                request_adapter = None

            if request_adapter is None:
                raise RuntimeError("Cannot refresh credentials: install google-auth[requests].")

            try:
                creds.refresh(request_adapter)
            except Exception as refresh_exc:
                # Common cause: refresh token revoked or invalid_grant
                # Provide explicit error so UI/terminal can show it.
                # Wrap into RuntimeError with clear message
                raise RuntimeError(f"Failed to refresh Google credentials: {refresh_exc}") from refresh_exc

            # persist refreshed info
            token_data.update({
                "token": creds.token,
                "refresh_token": creds.refresh_token or token_data.get("refresh_token"),
                "token_uri": getattr(creds, "token_uri", token_data.get("token_uri")),
                "client_id": creds.client_id or token_data.get("client_id"),
                "client_secret": creds.client_secret or token_data.get("client_secret"),
                "scopes": list(creds.scopes) if creds.scopes else token_data.get("scopes"),
            })
            token_row.token_json = json.dumps(token_data)
            try:
                db.add(token_row)
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
    except Exception as exc:
        # Provide helpful error (likely invalid_grant / revoked)
        raise RuntimeError(f"Failed to refresh credentials: {exc}") from exc

    # Compose MIME message
    mixed = MIMEMultipart()
    mixed["From"] = from_addr
    mixed["To"] = to_addrs
    if cc_addrs:
        mixed["Cc"] = cc_addrs
    if bcc_addrs:
        mixed["Bcc"] = bcc_addrs
    mixed["Subject"] = subject or ""
    mixed["Reply-To"] = from_addr
    try:
        mixed["Date"] = formatdate(localtime=True)
        mixed["Message-ID"] = _make_msgid(domain="gmail.com")
    except Exception:
        pass
    mixed["MIME-Version"] = "1.0"
    mixed["X-Mailer"] = "Teetli WorkUpdateApp"
    mixed["X-Priority"] = "1"

    body_part = MIMEText((body or "") + "<br><br>—<br><em>Sent securely via Teetli Work Update</em>", "html", _charset="utf-8")
    mixed.attach(body_part)

    if attachments:
        for up in attachments:
            try:
                filename = getattr(up, "filename", None) or "attachment"
                try:
                    content = up.file.read()
                    try:
                        up.file.seek(0)
                    except Exception:
                        pass
                except Exception:
                    content = None
                if not content:
                    continue
                part = MIMEBase("application", "octet-stream")
                part.set_payload(content)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                mixed.attach(part)
            except Exception:
                continue

    raw = base64.urlsafe_b64encode(mixed.as_bytes()).decode()

    # Helper to send (disables discovery cache to avoid oauth2client warning)
    def _do_send(creds_obj):
        try:
            service = build("gmail", "v1", credentials=creds_obj, cache_discovery=False)
            sent = service.users().messages().send(
                userId="me",
                body={
                    "raw": raw,
                    "labelIds": ["INBOX", "IMPORTANT"],
                    "sendAsEmail": from_addr
                }
            ).execute()
            return sent
        except Exception as e:
            # bubble up so caller can decide to retry
            raise e

    # Try send, if auth error try one refresh+retry
    try:
        return _do_send(creds)
    except Exception as first_exc:
        # try to detect 401/invalid_grant-like issues and retry refresh once
        try:
            from googleapiclient.errors import HttpError as GHttpError
            is_http_err = isinstance(first_exc, GHttpError) or (hasattr(first_exc, 'resp') and getattr(first_exc, 'resp', None) is not None)
        except Exception:
            is_http_err = False

        try_retry = False
        try:
            if hasattr(first_exc, 'resp') and getattr(first_exc, 'resp', None) is not None:
                try:
                    code = int(getattr(first_exc, 'resp').status)
                    if code == 401:
                        try_retry = True
                except Exception:
                    pass
            else:
                msg = str(first_exc).lower()
                if "401" in msg or "invalid_grant" in msg or "unauthorized" in msg or "revoked" in msg:
                    try_retry = True
        except Exception:
            try_retry = False

        if try_retry:
            # attempt refresh + retry
            try:
                try:
                    from google.auth.transport.requests import Request as GARequest
                    request_adapter = GARequest()
                except Exception:
                    request_adapter = None

                if request_adapter is None:
                    raise RuntimeError("Cannot refresh credentials (missing google-auth[requests]) to retry send.")

                creds.refresh(request_adapter)

                # persist refreshed tokens
                token_data.update({
                    "token": creds.token,
                    "refresh_token": creds.refresh_token or token_data.get("refresh_token"),
                    "token_uri": getattr(creds, "token_uri", token_data.get("token_uri")),
                    "client_id": creds.client_id or token_data.get("client_id"),
                    "client_secret": creds.client_secret or token_data.get("client_secret"),
                    "scopes": list(creds.scopes) if creds.scopes else token_data.get("scopes"),
                })
                token_row.token_json = json.dumps(token_data)
                try:
                    db.add(token_row)
                    db.commit()
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass

                return _do_send(creds)
            except Exception as retry_exc:
                # include both errors for debugging
                raise RuntimeError(f"Send failed (retry attempt also failed): {retry_exc}") from retry_exc

        # no retry attempted or retry failed
        raise RuntimeError(f"Gmail API send error: {first_exc}") from first_exc

# -------------------------
# OAuth configuration (Work-Update-specific env names)
# -------------------------
GOOGLE_CLIENT_ID = os.getenv("WORKUPD_GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("WORKUPD_GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("WORKUPD_GOOGLE_REDIRECT_URI")
GOOGLE_OAUTH_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GOOGLE_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URI = os.getenv("WORKUPD_GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")

# -------------------------
# Signing helper (uses SECRET_KEY env)
# -------------------------
_SECRET = os.getenv("SECRET_KEY") or os.getenv("SECRET") or os.getenv("APP_SECRET")
_signer = None
if URLSafeSerializer is not None and _SECRET:
    try:
        _signer = URLSafeSerializer(_SECRET, salt="workupdate-oauth")
    except Exception:
        _signer = None

def sign_uid(uid: int) -> Optional[str]:
    if not _signer:
        return None
    try:
        return _signer.dumps({"uid": int(uid)})
    except Exception:
        return None

def unsign_uid(signed: str) -> Optional[int]:
    if not _signer or not signed:
        return None
    try:
        data = _signer.loads(signed)
        if isinstance(data, dict) and "uid" in data:
            return int(data["uid"])
    except BadSignature:
        return None
    except Exception:
        return None
    return None

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
        pass

# -------------------------
# Routes (mostly unchanged)
# -------------------------
@router.get("/work-update/authorize")
def work_update_authorize(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(lambda: None) if get_current_user is None else Depends(get_current_user),
):
    if current_user is None:
        return RedirectResponse(url="/login?next=/work-update/authorize", status_code=302)

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_REDIRECT_URI:
        return templates.TemplateResponse("base.html", {
            "request": request,
            "user": current_user,
            "from_email": getattr(current_user, "email", ""),
            "manager_email": getattr(current_user, "manager_email", "") or os.getenv("DEFAULT_MANAGER_EMAIL", ""),
            "error": "Gmail OAuth is not configured on the server for Work-Update. Contact admin."
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
    return RedirectResponse(url=auth_url)

@router.get("/work-update/oauth2callback")
def work_update_oauth2callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    state_raw = request.query_params.get("state")
    error = request.query_params.get("error")
    if error or not code:
        return RedirectResponse(url="/work-update?authorized=0", status_code=303)

    # parse state for user id
    try:
        state = json.loads(state_raw) if state_raw else {}
        user_id = state.get("uid")
    except Exception:
        user_id = None

    # fallback attempt: try find user from cookies if state missing (best-effort)
    if not user_id:
        try:
            user_email = request.cookies.get("user_email")
            if user_email:
                gen = get_db()
                db_try = next(gen)
                try:
                    try:
                        from landing_page_app.models.user import User
                    except Exception:
                        User = None
                    if User is not None:
                        user_obj = db_try.query(User).filter(User.email == user_email).first()
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
            return templates.TemplateResponse("base.html", {
                "request": request,
                "error": "Authorized with Google but could not associate token with your user account (no user id found).",
                "user": None,
                "from_email": "",
                "manager_email": os.getenv("DEFAULT_MANAGER_EMAIL", "")
            }, status_code=500)

        # Persist token-related fields (store client_id/client_secret for refresh usage later)
        token_json = json.dumps({
            "token": token_resp.get("access_token"),
            "refresh_token": token_resp.get("refresh_token"),
            "token_uri": GOOGLE_TOKEN_URI,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "scopes": [GOOGLE_OAUTH_SCOPE]
        })

        token_obj = db.query(WorkupGoogleOAuthToken).filter(WorkupGoogleOAuthToken.user_id == int(user_id)).first()
        if token_obj:
            token_obj.token_json = token_json
        else:
            token_obj = WorkupGoogleOAuthToken(user_id=int(user_id), token_json=token_json)
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

    # Success landing page (shows confirmation) and sets helper signed cookie
    landing_html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Authorization successful</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body { font-family: Inter, Arial, sans-serif; background:#f8fafc; color:#0f172a; margin:0; display:flex; align-items:center; justify-content:center; height:100vh; }
    .card { background:#fff; padding:26px; border-radius:12px; box-shadow:0 10px 30px rgba(2,6,23,0.08); max-width:640px; text-align:center; }
    h1 { margin:6px 0 8px; font-size:20px; }
    p { color:#475569; margin:8px 0 16px; }
    .btn { display:inline-block; padding:10px 16px; border-radius:8px; text-decoration:none; font-weight:700; }
    .btn-primary { background:#0ea5a4; color:#fff; border:none; }
    .btn-plain { background:#fff; border:1px solid #e2e8f0; color:#0f172a; margin-left:8px; }
    .note { margin-top:14px; color:#94a3b8; font-size:13px; }
    .status { margin-top:12px; color:#64748b; font-size:14px; }
  </style>
</head>
<body>
  <div class="card" role="dialog" aria-modal="true">
    <div style="font-size:48px;color:#10b981;">✔</div>
    <h1>Google authorized ✔</h1>
    <p>Your Google account was connected successfully. Click Continue to go to Work Update or wait — we'll take you there automatically.</p>

    <div>
      <a id="continueBtn" class="btn btn-primary" href="/work-update?authorized=1">Continue to Work Update</a>
      <a id="homeBtn" class="btn btn-plain" href="/templates">Go to Home</a>
    </div>

    <div class="status" id="status">Checking app session…</div>
    <div class="note">If you are not signed in, please sign in and then click Continue.</div>
  </div>

  <script>
    (function(){
      const maxRetries = 10;
      const retryDelay = 900; // ms
      let attempts = 0;
      const statusEl = document.getElementById('status');

      function tryPoll() {
        attempts++;
        statusEl.textContent = 'Checking app session… (attempt ' + attempts + ' of ' + maxRetries + ')';
        fetch('/work-update/poll', { method: 'GET', credentials: 'include', redirect: 'manual' })
          .then(resp => {
            if (resp.status === 200) {
              window.location.href = '/work-update?authorized=1';
            } else if (resp.status === 401) {
              if (attempts < maxRetries) {
                setTimeout(tryPoll, retryDelay);
              } else {
                statusEl.textContent = 'Still not authenticated. Click Continue to retry after login, or use "Go to Home" to return.';
              }
            } else {
              if (attempts < maxRetries) {
                setTimeout(tryPoll, retryDelay);
              } else {
                statusEl.textContent = 'Could not confirm session. Use Continue to try or log in and then return.';
              }
            }
          })
          .catch(err => {
            if (attempts < maxRetries) {
              setTimeout(tryPoll, retryDelay);
            } else {
              statusEl.textContent = 'Network error while checking session. Click Continue to try again.';
            }
          });
      }

      setTimeout(tryPoll, 350);

      document.getElementById('continueBtn').addEventListener('click', function(e){
        e.preventDefault();
        attempts = 0;
        statusEl.textContent = 'Retrying…';
        tryPoll();
      });
    })();
  </script>
</body>
</html>
"""
    resp = HTMLResponse(content=landing_html, status_code=200)

    # helper cookie so frontend can show authorized toast if needed
    resp.set_cookie("has_google_token", "1", path="/", max_age=120, httponly=False, samesite="lax")

    # set signed helper cookie with uid so /work-update/poll can detect token present
    try:
        signed = sign_uid(user_id)
        if signed:
            resp.set_cookie(
                "oauth_uid", signed,
                path="/",
                max_age=120,
                httponly=False,
                samesite="None",   # allow cross-site
                secure=False        # useful for localhost (set True in prod)
            )

    except Exception:
        pass

    return resp

@router.get("/work-update/poll")
def work_update_poll(request: Request, db: Session = Depends(get_db), current_user=Depends(lambda: None) if get_current_user is None else Depends(get_current_user)):
    if current_user:
        return JSONResponse({"authenticated": True}, status_code=200)

    # check signed helper cookie
    try:
        signed = request.cookies.get("oauth_uid")
        uid = None
        if signed:
            uid = unsign_uid(signed)
        if uid:
            # ensure token row exists for this uid
            row = get_user_token_row(db, uid)
            if row:
                return JSONResponse({"authenticated": True, "using": "oauth_uid"}, status_code=200)
    except Exception:
        pass

    return JSONResponse({"detail": "Not authenticated"}, status_code=401)

@router.get("/work-update", response_class=HTMLResponse)
def work_update_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(lambda: None) if get_current_user is None else Depends(get_current_user),
):
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

# --- import add_user_log for activity logging (minimal change) ---
try:
    from landing_page_app.models.log import add_user_log
except Exception:
    def add_user_log(db: Session, user_id: int, action: str, commit: bool = False):
        return None

@router.post("/work-update/send")
def work_update_send(
    request: Request,
    from_email: str = Form(...),
    to_email: str = Form(...),
    subject: str = Form(""),
    body: str = Form(""),
    cc_email: str = Form(""),
    bcc_email: str = Form(""),
    attachments: List[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(lambda: None) if get_current_user is None else Depends(get_current_user),
):
    if current_user is None:
        return RedirectResponse(url="/login?next=/work-update", status_code=302)

    user_email = getattr(current_user, "email", None)
    if user_email and from_email.strip().lower() != user_email.strip().lower():
        from_email = user_email

    if not to_email:
        raise HTTPException(status_code=400, detail="Recipient (to) is required.")

    def normalize_list(s: Optional[str]) -> str:
        if not s:
            return ""
        parts = [p.strip() for p in s.replace(";", ",").split(",") if p and p.strip()]
        seen = set()
        out = []
        for p in parts:
            key = p.lower()
            if key not in seen:
                seen.add(key)
                out.append(p)
        return ", ".join(out)

    to_addrs = normalize_list(to_email)
    cc_addrs = normalize_list(cc_email)
    bcc_addrs = normalize_list(bcc_email)

    combined = to_addrs or cc_addrs or bcc_addrs

    user_id = getattr(current_user, "id", None)

    try:
        token_row = get_user_token_row(db, user_id) if user_id else None

        if token_row:
            try:
                send_via_gmail_api(
                    db=db,
                    user_id=int(user_id),
                    from_addr=from_email,
                    to_addrs=to_addrs,
                    subject=subject,
                    body=body,
                    cc_addrs=cc_addrs or None,
                    bcc_addrs=bcc_addrs or None,
                    attachments=attachments or None
                )
                # Log success (Gmail)
                try:
                    actor = getattr(current_user, "full_name", None) or getattr(current_user, "email", "Unknown User")
                    names = combined or ""
                    log_msg = f"{actor} sent message '{(subject or '').strip()}' to {names}"
                    add_user_log(db, getattr(current_user, "id", None), log_msg, commit=True)
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass

                return RedirectResponse(url="/work-update?sent=1", status_code=status.HTTP_302_FOUND)
            except Exception as exc:
                # Gmail failed -> try SMTP fallback (if configured)
                try:
                    smtp_user = os.getenv("SMTP_USERNAME")
                    smtp_pass = os.getenv("SMTP_PASSWORD")
                    if smtp_user and smtp_pass:
                        try:
                            send_email_smtp(from_email, to_addrs, subject, body, cc_addrs or None, bcc_addrs or None, attachments or None)

                            # log SMTP fallback
                            try:
                                actor = getattr(current_user, "full_name", None) or getattr(current_user, "email", "Unknown User")
                                names = combined or ""
                                log_msg = f"{actor} sent message '{(subject or '').strip()}' to {names} (via SMTP fallback)"
                                add_user_log(db, getattr(current_user, "id", None), log_msg, commit=True)
                            except Exception:
                                try:
                                    db.rollback()
                                except Exception:
                                    pass

                            return RedirectResponse(url="/work-update?sent=1", status_code=status.HTTP_302_FOUND)
                        except Exception:
                            pass
                except Exception:
                    pass

                # If Gmail & SMTP both failed
                return templates.TemplateResponse("base.html", {
                    "request": request,
                    "user": current_user,
                    "from_email": from_email,
                    "manager_email": combined,
                    "error": str(exc),
                    "subject": subject,
                    "body": body
                }, status_code=500)

        # No token_row -> try SMTP if configured
        smtp_user = os.getenv("SMTP_USERNAME")
        smtp_pass = os.getenv("SMTP_PASSWORD")
        if smtp_user and smtp_pass:
            try:
                send_email_smtp(from_email, to_addrs, subject, body, cc_addrs or None, bcc_addrs or None, attachments or None)
                # log success (SMTP)
                try:
                    actor = getattr(current_user, "full_name", None) or getattr(current_user, "email", "Unknown User")
                    names = combined or ""
                    log_msg = f"{actor} sent message '{(subject or '').strip()}' to {names} (via SMTP)"
                    add_user_log(db, getattr(current_user, "id", None), log_msg, commit=True)
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass

                return RedirectResponse(url="/work-update?sent=1", status_code=status.HTTP_302_FOUND)
            except Exception as exc:
                return templates.TemplateResponse("base.html", {
                    "request": request,
                    "user": current_user,
                    "from_email": from_email,
                    "manager_email": combined,
                    "error": str(exc),
                    "subject": subject,
                    "body": body
                }, status_code=500)

        # If no transport available
        return templates.TemplateResponse("base.html", {
            "request": request,
            "user": current_user,
            "from_email": from_email,
            "manager_email": combined,
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
            "manager_email": combined,
            "error": str(exc),
            "subject": subject,
            "body": body
        }, status_code=500)
