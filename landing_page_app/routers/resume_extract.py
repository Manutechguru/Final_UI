# resume_extract.py  (UPDATED for improved extraction accuracy + Relevant Exp fixes)
import os
import io
import re
import json
import time
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Request, Form, Cookie
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from landing_page_app.database import get_db
from landing_page_app.models.user import User, UserRole
from landing_page_app.models.log import UserLog
from landing_page_app.models import Candidate

import fitz  # PyMuPDF
from pdf2image import convert_from_bytes
import pytesseract
from docx import Document
import textract

import google.generativeai as genai
import gspread
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, HttpError

router = APIRouter(prefix="/admin", tags=["Admin: Resume Extract"])

# ==========================
# CONFIG
# ==========================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
SHEET_NAME = os.getenv("SHEET_NAME", "Resume")
TESSERACT_CMD = os.getenv("TESSERACT_CMD")

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

SCOPES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]

# ==========================
# GEMINI CONFIG
# ==========================
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel("gemini-2.0-flash-lite")
else:
    gemini_model = None

# ==========================
# AUTH HELPERS
# ==========================
def _is_admin_obj(user: User) -> bool:
    try:
        return getattr(user, "role", None) == UserRole.ADMIN
    except Exception:
        return str(getattr(user, "role", "")).upper() == "ADMIN"


def _require_admin_local(db: Session, user_email: Optional[str]):
    if not user_email:
        return None, RedirectResponse(url="/login?next=/admin", status_code=302)
    admin = db.query(User).filter(User.email == user_email).first()
    if not admin:
        return None, RedirectResponse(url="/login?next=/admin", status_code=302)
    if not _is_admin_obj(admin):
        return None, RedirectResponse(url="/templates/?error=access_denied", status_code=302)
    return admin, None


# ==========================
# GOOGLE AUTH (OAuth)
# ==========================
def _get_google_creds():
    creds = None
    token_file = "token.json"
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
        else:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_config(
                {
                    "installed": {
                        "client_id": GOOGLE_CLIENT_ID,
                        "client_secret": GOOGLE_CLIENT_SECRET,
                        "redirect_uris": ["http://localhost:8765/"],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                },
                SCOPES,
            )
            creds = flow.run_local_server(port=8765)
        with open(token_file, "w") as token:
            token.write(creds.to_json())
    return creds


def _drive_service():
    creds = _get_google_creds()
    return build("drive", "v3", credentials=creds)


def _gspread_client():
    creds = _get_google_creds()
    return gspread.authorize(creds)


# ==========================
# TEXT EXTRACTION (LOCAL)
# ==========================
def extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    text_parts = []
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as pdf:
            for page in pdf:
                t = page.get_text("text") or ""
                if t.strip():
                    text_parts.append(t)
    except Exception:
        pass
    text = "\n".join(text_parts).strip()

    # If extracted text is too short, fallback to OCR
    if len(text) < 200:
        try:
            images = convert_from_bytes(file_bytes)
            ocr_text = [pytesseract.image_to_string(img) for img in images]
            text = "\n".join(ocr_text).strip()
        except Exception:
            pass
    return text or ""


def extract_text_from_docx_bytes(file_bytes: bytes) -> str:
    try:
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join((para.text or "") for para in doc.paragraphs).strip()
    except Exception:
        return ""


def extract_text_from_doc_bytes(file_bytes: bytes) -> str:
    try:
        txt = textract.process(io.BytesIO(file_bytes), extension="doc")
        return txt.decode("utf-8").strip()
    except Exception:
        return ""


def extract_text_from_bytes_by_mime(fname: str, file_bytes: bytes) -> str:
    fname_lower = (fname or "").lower()
    if fname_lower.endswith(".pdf"):
        return extract_text_from_pdf_bytes(file_bytes)
    if fname_lower.endswith(".docx"):
        return extract_text_from_docx_bytes(file_bytes)
    if fname_lower.endswith(".doc"):
        return extract_text_from_doc_bytes(file_bytes)
    # fallback: try pdf parser then textract
    t = extract_text_from_pdf_bytes(file_bytes)
    if t and len(t) > 50:
        return t
    t2 = extract_text_from_docx_bytes(file_bytes) or extract_text_from_doc_bytes(file_bytes)
    return t2 or ""


# ==========================
# UTIL: Local validators & normalization
# ==========================
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?91|91|0)?\s*[-.\(\)\s]*([6-9]\d{9})")  # India-focused fallback: 10 digits starting 6-9

def normalize_email(email: str) -> str:
    if not email:
        return ""
    m = EMAIL_RE.search(email)
    return (m.group(0).lower() if m else email.strip())


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    # extract digits
    digits = re.sub(r"\D", "", phone or "")
    # Try to extract last 10 digits (common)
    if len(digits) >= 10:
        core = digits[-10:]
        if re.match(r"[6-9]\d{9}", core):
            return f"91{core}"
    # fallback: try PHONE_RE
    m = PHONE_RE.search(phone)
    if m:
        return f"91{m.group(1)}"
    return phone.strip()


DEGREE_KEYWORDS = [
    "phd", "doctor", "doctorate", "master", "m\.?s\.?", "mtech", "mba", "bachelor", "b\.?tech", "b\.?e\.?", "bsc", "b\.?com",
    "m\.?com", "msc", "bba", "associate"
]

def extract_education_from_text(text: str) -> str:
    if not text:
        return ""
    txt = text.lower()
    for kw in DEGREE_KEYWORDS:
        if re.search(r"\b" + kw + r"\b", txt):
            # return the first matching degree phrase (best-effort)
            # try to capture up to 5 words around the keyword
            m = re.search(r"([A-Za-z0-9,\-\/\s]{0,60}\b" + kw + r"\b[A-Za-z0-9,\-\/\s]{0,60})", text, re.IGNORECASE)
            if m:
                return " ".join(m.group(0).split())[:200]
            return kw
    return ""


def compute_experience_from_text(text: str) -> str:
    """
    Best-effort compute total IT experience:
    - Looks for explicit patterns like 'X years', 'X yrs', 'X years Y months'
    - Or identifies year ranges like 2015-2020 and computes diff between max and min year
    Returns string like '6 years' or '' if not found.
    """
    if not text:
        return ""
    # try pattern 'X years' first
    m = re.search(r"(\d+)\s*(?:years|yrs|year|yr)", text, re.IGNORECASE)
    if m:
        yrs = int(m.group(1))
        return f"{yrs} years"
    # try combined years+months
    m2 = re.search(r"(\d+)\s*years?\s*(?:and)?\s*(\d+)\s*months?", text, re.IGNORECASE)
    if m2:
        yrs = int(m2.group(1))
        mos = int(m2.group(2))
        if mos >= 12:
            yrs += mos // 12
            mos = mos % 12
        return f"{yrs} years {mos} months" if mos else f"{yrs} years"
    # try year ranges
    years = [int(y) for y in re.findall(r"\b(19|20)\d{2}\b", text)]
    if years:
        ymin, ymax = min(years), max(years)
        diff = max(0, ymax - ymin)
        if diff <= 1:
            return f"{diff} years"
        return f"{diff} years"
    return ""


def compute_relevant_experience_from_text(text: str, focus_keywords: Optional[List[str]] = None) -> str:
    """
    Best-effort compute relevant experience for the resume.
    - First looks for explicit 'Relevant Experience' phrases like 'Relevant Experience: X years'
    - Next, falls back to scanning for domain-specific keywords (if provided) and counts year mentions nearby.
    - Finally, falls back to overall IT experience (using compute_experience_from_text).
    Returns string like '3 years' or '' if not found.
    """
    if not text:
        return ""
    txt = text.lower()
    # 1) explicit pattern
    m = re.search(r"relevant experience[:\s]*([0-9]+)\s*(?:years|yrs|year|yr)", txt, re.IGNORECASE)
    if m:
        return f"{int(m.group(1))} years"

    # 2) e.g., "Relevant Experience: 2 years 6 months"
    m2 = re.search(r"relevant experience[:\s]*([0-9]+)\s*years?\s*(?:and)?\s*([0-9]+)\s*months?", txt, re.IGNORECASE)
    if m2:
        yrs = int(m2.group(1)); mos = int(m2.group(2))
        if mos >= 12:
            yrs += mos // 12
            mos = mos % 12
        return f"{yrs} years {mos} months" if mos else f"{yrs} years"

    # 3) if focus keywords provided, try to estimate years by looking for year patterns near those keywords
    if focus_keywords:
        for kw in focus_keywords:
            pattern = rf"(\d+)\s*(?:years|yrs|year|yr)\s*(?:of)?\s*(?:.*{re.escape(kw)}|{re.escape(kw)}.*)"
            m3 = re.search(pattern, txt, re.IGNORECASE)
            if m3:
                return f"{int(m3.group(1))} years"

    # 4) fallback to overall IT experience
    return compute_experience_from_text(text)


def normalize_name(name: str) -> str:
    if not name:
        return ""
    # simple title case but preserve common uppercase abbreviations (e.g., "PHP")
    parts = name.strip().split()
    new_parts = []
    for p in parts:
        if p.isupper() and len(p) <= 4:
            new_parts.append(p.upper())
        else:
            new_parts.append(p.capitalize())
    return " ".join(new_parts)


def normalize_skilllist(skill_text: str) -> str:
    if not skill_text:
        return ""
    # split on commas/pipe/semicolon/newline and dedupe
    parts = re.split(r"[,\|\;\n]", skill_text)
    cleaned = []
    seen = set()
    for p in parts:
        pp = p.strip()
        if not pp:
            continue
        pp = re.sub(r"\s{2,}", " ", pp)
        key = pp.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(pp)
    return ", ".join(cleaned[:20])  # limit to top 20 skills


# ==========================
# DRIVE HELPERS
# ==========================
def _extract_folder_id_from_link(link: str) -> str:
    if not link:
        return ""
    m = re.search(r"/folders/([a-zA-Z0-9_-]{10,})", link)
    if m:
        return m.group(1)
    m2 = re.search(r"id=([a-zA-Z0-9_-]{10,})", link)
    if m2:
        return m2.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{10,}", link):
        return link
    return ""


def _list_files_in_folder(folder_id: str):
    ds = _drive_service()
    q = f"'{folder_id}' in parents and trashed=false"
    results = ds.files().list(q=q, fields="files(id, name, mimeType)").execute()
    return results.get("files", [])


def _download_file_bytes(file_id: str) -> bytes:
    ds = _drive_service()
    req = ds.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue()


# ==========================
# GEMINI PROMPT BUILDERS (improved)
# ==========================
def _build_resume_prompt_from_text(text: str, resume_url: str) -> str:
    # Single-resume extraction prompt (strict JSON array output)
    return f"""
You are an extremely literal AI Resume Extractor. Read the resume text delimited between <<<RESUME>>> markers and output ONLY a valid JSON array containing exactly one object with these fields (use exact keys):

"Candidate Name", "Email ID", "Contact Number", "Location", "Skillset",
"IT Exp.", "Relevant Exp.", "Education", "Company", "Client", "ResumeLink", "Comment", "notice_period"

Rules:
- Output valid JSON array only, nothing else.
- If a field is missing, set "" (empty string). Do not omit fields.
- Normalize phone to digits only (we will further normalize locally). Format email lowercase.
- "ResumeLink" must be exactly: "{resume_url}"
- Keep "Comment" short (1-3 lines) and factual: one sentence about strengths and one about gaps.
- For "Skillset" separate skills by commas.
- For "IT Exp." provide best estimate like '5 years' or '3 years 6 months'.

<<<RESUME>>>
{text}
<<<RESUME>>>
Return ONLY the JSON array.
""".strip()


def _build_validation_prompt(original_text: str, candidate_json: dict) -> str:
    # Ask Gemini to validate & normalize extracted fields (phone -> 91xxxxxxxxxx, email lowercase,
    # ensure name capitalization, ensure IT Exp. consistent) — now explicitly asking for Relevant Exp.
    cj = json.dumps(candidate_json, ensure_ascii=False)
    return f"""
You are a data normalizer. Given the original resume text (between <<<RESUME>>> markers) and the extracted JSON (between <<<JSON>>> markers), return ONLY a corrected/normalized JSON array (same shape) with the following rules:

- Normalize "Email ID" to lowercase.
- Normalize "Contact Number" to the format '91XXXXXXXXXX' if possible.
- Normalize "Candidate Name" to proper capitalization.
- Normalize "Relevant Exp." to a concise value like '3 years' or '2 years 6 months'. If the resume contains a 'Relevant Experience' section or mentions domain-specific experience, compute the best estimate and fill here.
- If "IT Exp." is missing or clearly wrong, compute best estimate using the resume text.
- If "Education" is empty, try to extract highest degree from the resume text.
- If "Skillset" is empty or messy, extract up to 20 top skills as comma-separated values.
- Do NOT add any extra fields. Use an array with a single object.
- Keep all fields; missing remains empty string only if unknown.

<<<RESUME>>>
{original_text}
<<<RESUME>>>

<<<JSON>>>
{cj}
<<<JSON>>>

Return ONLY the corrected JSON array.
""".strip()


# ==========================
# GEMINI CALL
# ==========================
def _call_gemini(prompt: str, max_retries: int = 4) -> str:
    if not gemini_model:
        raise RuntimeError("Gemini not configured (GEMINI_API_KEY missing).")
    delay = 1.5
    for attempt in range(1, max_retries + 1):
        try:
            resp = gemini_model.generate_content(prompt)
            return (resp.text or "").strip()
        except Exception as e:
            msg = str(e).lower()
            # backoff on common transient errors
            if any(code in msg for code in ["429", "quota", "503", "500", "timeout"]):
                time.sleep(delay)
                delay = min(delay * 2, 20)
                continue
            # non-transient: re-raise so caller can skip that file
            raise
    return ""


def _extract_json_block(s: str):
    if not s:
        return None
    # first try to find JSON array block
    m = re.search(r"\[\s*{.*}\s*\]", s, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    # try to parse the whole string as JSON
    try:
        return json.loads(s)
    except Exception:
        return None


# ==========================
# SHEET HANDLER
# ==========================
SHEET_COLUMNS = [
    "Candidate Name", "Email ID", "Contact Number", "Location", "Skillset",
    "Relevant Exp.", "IT Exp.", "Education", "Company", "Client",
    "ResumeLink", "Comment", "notice_period", "recruitment_notes", "ai_score", "ai_explanation"
]


def _append_row_to_sheet(gclient, row_dict: dict):
    try:
        sheet = gclient.open(SHEET_NAME).sheet1
    except Exception:
        sh = gclient.create(SHEET_NAME)
        sheet = sh.sheet1
        sheet.append_row(SHEET_COLUMNS)

    header = sheet.row_values(1)
    if not header or len(header) < len(SHEET_COLUMNS):
        sheet.clear()
        sheet.append_row(SHEET_COLUMNS)

    row = [str(row_dict.get(col, "") or "") for col in SHEET_COLUMNS]
    sheet.append_row(row, value_input_option="USER_ENTERED")


# ==========================
# MAIN ROUTE (keeps your routing and DB logic; improved internal flow)
# ==========================
@router.post("/extract-resumes")
def extract_resumes_endpoint(
    request: Request,
    drive_link: str = Form(...),
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    admin, redirect = _require_admin_local(db, user_email)
    if redirect:
        return redirect

    folder_id = _extract_folder_id_from_link(drive_link.strip())
    if not folder_id:
        return RedirectResponse(url="/admin?tab=uploadcsv&error=Invalid+Drive+folder+link", status_code=302)

    try:
        files = _list_files_in_folder(folder_id)
    except Exception as e:
        return RedirectResponse(url=f"/admin?tab=uploadcsv&error=Drive+access+failed:+{quote_plus(str(e))}", status_code=302)

    if not files:
        return RedirectResponse(url="/admin?tab=uploadcsv&error=No+files+found+in+folder", status_code=302)

    gclient = _gspread_client()
    inserted = 0
    duplicates = []

    for f in files:
        file_id = f.get("id")
        fname = f.get("name")
        mime = f.get("mimeType", "").lower()
        resume_url = f"https://drive.google.com/file/d/{file_id}/view"

        # Download file bytes from Google Drive
        try:
            file_bytes = _download_file_bytes(file_id)
        except HttpError:
            # skip files we cannot download
            continue

        # 1) Extract text locally (best-effort). This helps accuracy massively.
        try:
            resume_text = extract_text_from_bytes_by_mime(fname, file_bytes)
        except Exception:
            resume_text = ""

        # If local extraction produced almost nothing, as a fallback keep file upload path to Gemini
        use_upload_to_gemini = False
        if not resume_text or len(resume_text) < 100:
            use_upload_to_gemini = True

        parsed = None
        raw_response = ""

        # 2) Primary path: use local text + Gemini extraction + validation
        try:
            if not use_upload_to_gemini:
                prompt = _build_resume_prompt_from_text(resume_text, resume_url)
                raw_response = _call_gemini(prompt)
                parsed = _extract_json_block(raw_response)
                # if Gemini returned something, run a validation/normalization pass
                if parsed and isinstance(parsed, list) and len(parsed) == 1:
                    candidate_obj = parsed[0]
                    # call validation prompt to normalize fields (now includes Relevant Exp.)
                    val_prompt = _build_validation_prompt(resume_text, candidate_obj)
                    val_raw = _call_gemini(val_prompt)
                    val_parsed = _extract_json_block(val_raw)
                    if val_parsed and isinstance(val_parsed, list) and len(val_parsed) == 1:
                        parsed = val_parsed
                    else:
                        # keep original parsed if validation failed
                        parsed = parsed
            else:
                # Fallback: upload file to Gemini (legacy behavior) if local text empty
                # preserve your existing logic but still perform validation step using extracted raw text (if any)
                try:
                    if fname.lower().endswith(".pdf"):
                        mime_type = "application/pdf"
                    elif fname.lower().endswith(".docx"):
                        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    elif fname.lower().endswith(".doc"):
                        mime_type = "application/msword"
                    else:
                        mime_type = "application/octet-stream"

                    uploaded_file = genai.upload_file(
                        io.BytesIO(file_bytes),
                        mime_type=mime_type,
                        display_name=fname
                    )

                    prompt = f"""
                    You are an AI Resume Extractor.

                    Read the attached resume and output ONLY a valid JSON array with one entry containing these fields:
                    "Candidate Name", "Email ID", "Contact Number", "Location", "Skillset",
                    "IT Exp.", "Relevant Exp.", "Education", "Company", "Client", "ResumeLink", "Comment", "notice_period".

                    Format phone as '91XXXXXXXXXX', fill missing as "", and always include:
                    "ResumeLink": "{resume_url}"
                    """

                    response = gemini_model.generate_content([prompt, uploaded_file])
                    raw_response = (response.text or "").strip()
                    parsed = _extract_json_block(raw_response)

                    # validation pass: use whatever text we have (may be empty) to attempt normalization
                    if parsed and isinstance(parsed, list) and len(parsed) == 1:
                        val_prompt = _build_validation_prompt(resume_text or "", parsed[0])
                        val_raw = _call_gemini(val_prompt)
                        val_parsed = _extract_json_block(val_raw)
                        if val_parsed and isinstance(val_parsed, list) and len(val_parsed) == 1:
                            parsed = val_parsed
                except Exception as e:
                    print("Gemini upload fallback error:", e)
                    parsed = None
        except Exception as e:
            print("Gemini extraction/validation error:", e)
            parsed = None

        if not parsed:
            # as a safety fallback, attempt to extract basic email/phone from resume_text using regex
            if resume_text:
                email_m = EMAIL_RE.search(resume_text)
                phone_m = PHONE_RE.search(resume_text)
                candidate_guess = {
                    "Candidate Name": "",
                    "Email ID": email_m.group(0) if email_m else "",
                    "Contact Number": normalize_phone(phone_m.group(1)) if phone_m else "",
                    "Location": "",
                    "Skillset": "",
                    "IT Exp.": compute_experience_from_text(resume_text),
                    "Relevant Exp.": compute_relevant_experience_from_text(resume_text),
                    "Education": extract_education_from_text(resume_text),
                    "Company": "",
                    "Client": "",
                    "ResumeLink": resume_url,
                    "Comment": "",
                    "notice_period": ""
                }
                parsed = [candidate_guess]
            else:
                continue

        # parsed is expected to be a list of candidate dicts (often length 1)
        for c in parsed:
            # defensive get with alternative keys in case Gemini used slightly different keys
            email = normalize_email(c.get("Email ID", "") or c.get("email", ""))
            name = normalize_name(c.get("Candidate Name", "") or c.get("name", ""))
            contact = normalize_phone(c.get("Contact Number", "") or c.get("contact", ""))

            # further local fallbacks using resume_text
            if not email and resume_text:
                m = EMAIL_RE.search(resume_text)
                if m:
                    email = normalize_email(m.group(0))
            if (not contact or len(re.sub(r"\D", "", contact)) < 10) and resume_text:
                pm = PHONE_RE.search(resume_text)
                if pm:
                    contact = normalize_phone(pm.group(1))

            skillset = normalize_skilllist(c.get("Skillset", "") or "")
            it_exp = c.get("IT Exp.", "") or compute_experience_from_text(resume_text)
            # Relevant experience: use parsed -> fallback compute -> final fallback to IT Exp.
            relevant_exp = c.get("Relevant Exp.", "") or compute_relevant_experience_from_text(resume_text)
            if not relevant_exp:
                relevant_exp = it_exp or ""
            education = c.get("Education", "") or extract_education_from_text(resume_text)
            company = c.get("Company", "") or ""
            client = c.get("Client", "") or ""
            comment = c.get("Comment", "") or ""
            notice_period = c.get("notice_period", "") or ""

            # Avoid duplicates (your existing logic)
            if email:
                exists = db.query(Candidate).filter(Candidate.email == email).first()
            else:
                exists = db.query(Candidate).filter(Candidate.candidate_name == name, Candidate.contact == contact).first()
            if exists:
                duplicates.append(email or f"{name}-{contact}")
                continue

            candidate = Candidate(
                candidate_name=name,
                contact=contact,
                email=email,
                location=c.get("Location", ""),
                skillset=skillset,
                relevant_experience=relevant_exp,
                it_experience=it_exp,
                education=education,
                company=company,
                clients=client,
                resumelinks=resume_url,
                comment=comment,
                notice_period=notice_period,
                recruitment_notes="",
                ai_score=None,
                ai_explanation="",
            )
            db.add(candidate)
            db.flush()
            inserted += 1

            # Append to sheet with normalized values
            _append_row_to_sheet(gclient, {
                "Candidate Name": name,
                "Email ID": email,
                "Contact Number": contact,
                "Location": c.get("Location", "") or "",
                "Skillset": skillset,
                "Relevant Exp.": relevant_exp,
                "IT Exp.": it_exp,
                "Education": education,
                "Company": company,
                "Client": client,
                "ResumeLink": resume_url,
                "Comment": comment,
                "notice_period": notice_period,
                "recruitment_notes": "",
                "ai_score": "",
                "ai_explanation": "",
            })

        # cleanup: if we used uploaded_file earlier, attempt to delete
        try:
            if 'uploaded_file' in locals():
                # delete by name if available (best-effort)
                try:
                    genai.delete_file(uploaded_file.name)
                except Exception:
                    pass
                del uploaded_file
        except Exception:
            pass

    db.add(UserLog(user_id=admin.id, action=f"Resume extraction from folder={folder_id}, inserted={inserted}, duplicates={len(duplicates)}"))
    db.commit()

    return RedirectResponse(
        url=f"/admin?tab=uploadcsv&msg=Extraction+completed+({inserted}+rows)&duplicates={quote_plus(','.join(duplicates))}",
        status_code=302,
    )
