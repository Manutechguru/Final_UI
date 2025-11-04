# landing_page_app/routers/candidates/gmail.py
import os
import re
import io
import json
import tempfile
import mimetypes
from typing import List, Optional
from fastapi import APIRouter, Request, Depends, Query, Body, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
from base64 import urlsafe_b64encode
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os.path

from landing_page_app.config import templates
from landing_page_app.database import get_db
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.jobs import Job
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.deps import get_current_user
from landing_page_app.models.user import User
from googleapiclient.discovery import build

# new imports for client lookup and logging
from landing_page_app.models.clients import Client
from landing_page_app.models.log import add_user_log

router = APIRouter(prefix="/candidates", tags=["Candidates - Gmail"])

# -------------------------
# Environment & scopes
# -------------------------
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_OAUTH_REDIRECT = os.getenv("GOOGLE_OAUTH_REDIRECT", "")
TOKEN_STORE_PATH = os.getenv("GMAIL_TOKEN_STORE_PATH", "gmail_tokens.json")

# note: order here doesn't matter too much but include drive if download/export required
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive",
]


# -------------------------
# token store helpers
# -------------------------
def _load_store() -> dict:
    if os.path.exists(TOKEN_STORE_PATH):
        try:
            with open(TOKEN_STORE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_store(store: dict):
    with open(TOKEN_STORE_PATH, "w") as f:
        json.dump(store, f)


def _save_creds(uid: str, creds: dict):
    store = _load_store()
    store[str(uid)] = creds
    _save_store(store)


def _delete_creds(uid: str):
    store = _load_store()
    if str(uid) in store:
        del store[str(uid)]
        _save_store(store)


def _get_creds(uid: str) -> Optional[dict]:
    return _load_store().get(str(uid))


# -------------------------
# OAuth flow builder & service factory
# -------------------------
def _flow(state: Optional[str] = None) -> Flow:
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_OAUTH_REDIRECT):
        raise RuntimeError("Missing Google OAuth environment variables (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT).")
    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_OAUTH_REDIRECT],
        }
    }
    return Flow.from_client_config(client_config=client_config, scopes=SCOPES, redirect_uri=GOOGLE_OAUTH_REDIRECT, state=state)


def _service(uid: str, name: str, ver: str):
    """Build google api service for stored credentials for user uid (string)"""
    c = _get_creds(uid)
    if not c:
        return None
    # Credentials expects certain keys - supplied when we save in callback
    creds = Credentials(
        token=c.get("token"),
        refresh_token=c.get("refresh_token"),
        token_uri=c.get("token_uri"),
        client_id=c.get("client_id"),
        client_secret=c.get("client_secret"),
        scopes=c.get("scopes")
    )
    return build(name, ver, credentials=creds)


# -------------------------
# helpers: embed link + download/export
# -------------------------
def make_embed_link(url: str) -> str:
    """Convert google links to their /preview equivalents for iframe embedding."""
    if not url:
        return ""
    url = url.strip()
    m = re.search(r"/d/([^/]+)/", url)
    if m:
        return f"https://drive.google.com/file/d/{m.group(1)}/preview"
    m = re.search(r"docs\.google\.com/document/d/([^/]+)/", url)
    if m:
        return f"https://docs.google.com/document/d/{m.group(1)}/preview"
    m = re.search(r"docs\.google\.com/spreadsheets/d/([^/]+)/", url)
    if m:
        return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/preview"
    m = re.search(r"docs\.google\.com/presentation/d/([^/]+)/", url)
    if m:
        return f"https://docs.google.com/presentation/d/{m.group(1)}/preview"
    return url


def download_drive_file(drive_service, drive_url: str) -> Optional[str]:
    """
    Download or export a Drive/Docs/Sheets file to a temporary local file and return its path.
    Caller should delete the returned path after use.
    """
    if not drive_service or not drive_url:
        return None
    m = re.search(r"/d/([^/]+)/", drive_url)
    if not m:
        return None
    file_id = m.group(1)
    try:
        meta = drive_service.files().get(fileId=file_id, fields="name,mimeType").execute()
        name = meta.get("name", file_id)
        mime = meta.get("mimeType", "")
        # safe suffix
        suffix = "_" + re.sub(r"[^\w\.-]+", "_", name)
        fd, tmp_path = tempfile.mkstemp(prefix="gmail_", suffix=suffix)
        os.close(fd)
        fh = io.FileIO(tmp_path, "wb")
        # export if native Google type
        if mime.startswith("application/vnd.google-apps"):
            export_mime = "application/pdf"
            request = drive_service.files().export_media(fileId=file_id, mimeType=export_mime)
        else:
            request = drive_service.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.close()
        return tmp_path
    except HttpError as e:
        # permission or other errors
        print("Drive download error:", e)
        return None
    except Exception as e:
        print("Drive download unexpected error:", e)
        return None


# -------------------------
# Compose page
# -------------------------
@router.get("/gmail/compose", response_class=HTMLResponse)
def gmail_compose_page(
    request: Request,
    mode: str = Query("candidates"),
    candidate_ids: str = Query(""),
    jd_id: Optional[int] = Query(None),
    db = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Render compose page. Returns embed-friendly preview links (jd_link / preview_links).
    """
    try:
        ids = [int(x) for x in candidate_ids.split(",") if x.strip()] if candidate_ids else []
    except Exception:
        ids = []

    candidates = db.query(Candidate).filter(Candidate.candidates_id.in_(ids)).all() if ids else []
    to_emails = [c.email for c in candidates if c.email] if mode == "candidates" else []

    jd_link = None
    preview_links: List[str] = []
    body_html = ""

    if mode == "candidates":
        job = None
        if jd_id:
            job = db.query(Job).filter(Job.job_id == jd_id).first()
        else:
            if ids:
                mapping = db.query(CandidateJDMapping).filter(CandidateJDMapping.candidate_id == ids[0]).first()
                if mapping:
                    job = db.query(Job).filter(Job.job_id == mapping.jd_id).first()
        if job:
            jd_raw = (job.job_description or "").strip()
            jd_link = make_embed_link(jd_raw) if jd_raw else None
            body_html = f"<p>Dear Candidate,</p><p>Please find attached the JD for <b>{job.job_title or 'the role'}</b>.</p>"
        else:
            body_html = "<p>Dear Candidate,</p><p>Please find the JD attached.</p>"

    elif mode == "clients":
        for c in candidates:
            if c.resumelinks:
                for link in c.resumelinks.split(","):
                    link = link.strip()
                    if not link:
                        continue
                    preview_links.append(make_embed_link(link))
        body_html = "<p>Dear Client,</p><p>Attached are the shortlisted candidate resumes. Please find details below.</p>"

    # compute has_google_token for template (controls authorize button visibility)
    has_google_token = bool(_get_creds(user.id))

    creds_data = _get_creds(user.id)
    from_email = creds_data.get("authorized_email") if creds_data and creds_data.get("authorized_email") else user.email

    return templates.TemplateResponse("gmail_compose.html", {
        "request": request,
        "user": user,
        "from_email": from_email,
        "to_emails": ", ".join(to_emails),
        "mode": mode,
        "candidate_ids": candidate_ids or "",
        "jd_id": jd_id or "",
        "body_html": body_html,
        "jd_link": jd_link,
        "preview_links": preview_links,
        "has_google_token": has_google_token
    })


# -------------------------
# Simple check-auth endpoint for frontend convenience
# -------------------------
@router.get("/gmail/check-auth")
def gmail_check_auth(user: User = Depends(get_current_user)):
    creds = _get_creds(user.id)
    return {"authorized": bool(creds)}


# -------------------------
# OAuth flow endpoints
# -------------------------
@router.get("/gmail/auth")
def gmail_auth_start(
    request: Request,
    redirect_uri: Optional[str] = Query("/candidates/gmail/compose"),
    user: User = Depends(get_current_user)
):
    """
    Start the OAuth flow and return Redirect to Google consent screen.
    Preserves the intended redirect URI after successful auth.
    """
    # include redirect_uri in the state so we can return the user there later
    state = json.dumps({"uid": str(user.id), "redirect": redirect_uri})
    flow = _flow(state)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state
    )
    return RedirectResponse(auth_url)
@router.get("/gmail/callback")
def gmail_oauth_callback(code: Optional[str] = None, state: Optional[str] = None):
    """
    Callback: exchange code for tokens. Redirect back to previous page or compose screen.
    """
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    try:
        # Parse possible JSON state (contains uid + redirect)
        try:
            state_data = json.loads(state)
            uid = state_data.get("uid")
            redirect_uri = state_data.get("redirect", "/candidates/gmail/compose")
        except Exception:
            uid = state
            redirect_uri = "/candidates/gmail/compose"

        flow = _flow(state)
        flow.fetch_token(code=code)
        creds = flow.credentials

         # ---- NEW: fetch authorized Gmail email ----
        userinfo_service = build("oauth2", "v2", credentials=creds)
        userinfo = userinfo_service.userinfo().get().execute()
        authorized_email = userinfo.get("email")
        
        cred_dict = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
            "authorized_email": authorized_email,
        }
        _save_creds(uid, cred_dict)

        # ✅ redirect user back to intended page instead of root
        return RedirectResponse(redirect_uri)
    except Exception as e:
        msg = str(e)
        print("OAuth callback error:", msg)
        try:
            _delete_creds(state)
        except Exception:
            pass
        try:
            flow2 = _flow(str(state))
            auth_url2, _ = flow2.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
                state=str(state)
            )
            return RedirectResponse(auth_url2)
        except Exception:
            raise HTTPException(status_code=500, detail="OAuth error during callback. Please re-authorize.")

# -------------------------
# create message + send (attachments supported)
# -------------------------
def _make_message_with_attachments(from_addr: str, to_addrs: List[str], cc_addrs: List[str], bcc_addrs: List[str], subject: str, html: str, file_paths: List[str]):
    """
    Build a MIME message with optional attachments and return {'raw': base64urlencoded}.
    Sets To, Cc, Bcc headers as provided.
    """
    msg = MIMEMultipart()
    msg["from"] = from_addr
    if to_addrs:
        msg["to"] = ", ".join(to_addrs)
    if cc_addrs:
        msg["cc"] = ", ".join(cc_addrs)
    if bcc_addrs:
        msg["bcc"] = ", ".join(bcc_addrs)
    msg["subject"] = subject or ""
    msg.attach(MIMEText(html or "", "html"))
    for p in file_paths:
        if not p or not os.path.exists(p):
            continue
        ctype, _ = mimetypes.guess_type(p)
        ctype = ctype or "application/octet-stream"
        try:
            main, sub = ctype.split("/", 1)
        except Exception:
            main, sub = ("application", "octet-stream")
        with open(p, "rb") as f:
            part = MIMEBase(main, sub)
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(p)}"')
        msg.attach(part)
    raw = urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


@router.post("/gmail/send")
def gmail_send_email(payload: dict = Body(...), user: User = Depends(get_current_user), db = Depends(get_db)):
    """
    payload: { to, cc, bcc, subject, body_html, mode, jd_id, candidate_ids }
    Logging: writes human-friendly messages using the user's full_name, job title, client name and candidate names.
    """
    to_field = (payload.get("to") or "").strip()
    subject = payload.get("subject", "")
    body_html = payload.get("body_html", "")
    mode = payload.get("mode", "candidates")
    jd_id = payload.get("jd_id", None)
    candidate_ids = payload.get("candidate_ids", "")

    cc_field = (payload.get("cc") or "").strip()
    bcc_field = (payload.get("bcc") or "").strip()

    if not to_field and not cc_field and not bcc_field:
        raise HTTPException(status_code=400, detail="At least one recipient required (To, Cc, or Bcc)")

    to_emails = [e.strip() for e in to_field.split(",") if e.strip()] if to_field else []
    cc_emails = [e.strip() for e in cc_field.split(",") if e.strip()] if cc_field else []
    bcc_emails = [e.strip() for e in bcc_field.split(",") if e.strip()] if bcc_field else []

    # Build services
    gmail_svc = _service(str(user.id), "gmail", "v1")
    drive_svc = _service(str(user.id), "drive", "v3")

    # If either service missing -> return explicit needs_auth with auth_url
    if not gmail_svc or not drive_svc:
        # Provide an auth_url back so frontend can redirect automatically
        try:
            flow = _flow(str(user.id))
            auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent", state=str(user.id))
        except Exception:
            auth_url = "/candidates/gmail/auth"
        return JSONResponse({"error": "Gmail/Drive not authorized", "needs_auth": True, "auth_url": auth_url}, status_code=403)

    temp_files: List[str] = []
    attachments: List[str] = []

    try:
        # ----- prepare candidate list and names for logging -----
        ids = []
        if candidate_ids:
            try:
                ids = [int(x) for x in candidate_ids.split(",") if x.strip()]
            except Exception:
                ids = []

        candidates = db.query(Candidate).filter(Candidate.candidates_id.in_(ids)).all() if ids else []
        # use candidate_name (your model) and fallback to email
        candidate_names = [ (getattr(c, "candidate_name", None) or c.email or f"#{getattr(c, 'candidates_id', '')}") for c in candidates ]

        # metadata for logging
        client_name = None
        job_title = None

        # ----- candidates mode: attach JD -----
        if mode == "candidates":
            job = None
            if jd_id:
                job = db.query(Job).filter(Job.job_id == int(jd_id)).first()
            if not job and ids:
                mapping = db.query(CandidateJDMapping).filter(CandidateJDMapping.candidate_id == ids[0]).first()
                if mapping:
                    job = db.query(Job).filter(Job.job_id == mapping.jd_id).first()
            if job:
                job_title = job.job_title
                link = (job.job_description or "").strip()
                if ("drive.google.com" in link) or ("docs.google.com" in link):
                    p = download_drive_file(drive_svc, link)
                    if p:
                        attachments.append(p); temp_files.append(p)
                else:
                    if os.path.exists(link):
                        attachments.append(link)

        # ----- clients mode: attach candidate resumes -----
        elif mode == "clients" and candidates:
            # Attempt to derive client name from first candidate mapping -> job -> manager -> client
            try:
                mapping = db.query(CandidateJDMapping).filter(CandidateJDMapping.candidate_id == candidates[0].candidates_id).first()
                if mapping:
                    job = db.query(Job).filter(Job.job_id == mapping.jd_id).first()
                    if job and getattr(job, "manager", None):
                        client = db.query(Client).filter(Client.client_id == job.manager.client_id).first()
                        if client:
                            client_name = client.client_name
            except Exception:
                client_name = None

            # Attach resumes (drive or local files)
            for c in candidates:
                if c.resumelinks:
                    for raw_link in c.resumelinks.split(","):
                        link = raw_link.strip()
                        if not link:
                            continue
                        if ("drive.google.com" in link) or ("docs.google.com" in link):
                            p = download_drive_file(drive_svc, link)
                            if p:
                                attachments.append(p); temp_files.append(p)
                        else:
                            if os.path.exists(link):
                                attachments.append(link)

        # Create raw message + send
        raw_msg = _make_message_with_attachments(
            from_addr=user.email,
            to_addrs=to_emails,
            cc_addrs=cc_emails,
            bcc_addrs=bcc_emails,
            subject=subject,
            html=body_html,
            file_paths=attachments
        )
        send_resp = gmail_svc.users().messages().send(userId="me", body=raw_msg).execute()

        # ------------------------
        # Log a friendly action
        # ------------------------
        try:
            user_name = getattr(user, "full_name", user.email)
            if mode == "candidates" and job_title:
                names = ", ".join(candidate_names) if candidate_names else ", ".join(to_emails)
                log_msg = f"{user_name} sent message job details for '{job_title}' to candidates: {names}"
            elif mode == "clients" and client_name:
                names = ", ".join(candidate_names) if candidate_names else ", ".join(to_emails)
                log_msg = f"{user_name} sent message resumes of {names} candidates to client {client_name}"
            else:
                # generic fallback
                log_msg = f"{user_name} sent email"
            add_user_log(db, user.id, log_msg, commit=True)
        except Exception:
            # Do not break the send on logging errors
            try:
                db.rollback()
            except Exception:
                pass

        return JSONResponse({"message": "Email sent", "result": send_resp})
    except HttpError as he:
        print("Gmail API HttpError:", he)
        return JSONResponse({"error": "Gmail API error", "detail": str(he)}, status_code=500)
    except Exception as e:
        print("Send exception:", e)
        raise HTTPException(status_code=500, detail=f"Send failed: {str(e)}")
    finally:
        for f in temp_files:
            try:
                os.remove(f)
            except Exception:
                pass
