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

from groq import Groq
from landing_page_app.services.embedding_service import embed_text
import gspread
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, HttpError

router = APIRouter(prefix="/admin", tags=["Admin: Resume Extract"])

# ==========================
# CONFIG
# ==========================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
SHEET_NAME = os.getenv("SHEET_NAME", "Resume")
TESSERACT_CMD = os.getenv("TESSERACT_CMD")

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

SCOPES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]


GROQ_RESUME_API_KEY = os.getenv("GROQ_RESUME_API_KEY", "")
if not GROQ_RESUME_API_KEY:
    raise RuntimeError("GROQ_RESUME_API_KEY not set")

groq_client = Groq(api_key=GROQ_RESUME_API_KEY)



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


def _build_groq_batch_prompt(resumes: list[dict]) -> str:
    return f"""
You are a STRICT JSON generator.

You MUST return ONLY a valid JSON array.
NO explanations.
NO markdown.
NO text outside JSON.

If you cannot extract a field, return "" (empty string).

JSON schema (MUST MATCH EXACTLY):
[
  {{
    "candidate_name": "",
    "email": "",
    "contact": "",
    "location": "",
    "skillset": "",
    "it_experience": "",
    "relevant_experience": "",
    "education": "",
    "company": "",
    "clients": "",
    "resumelinks": "",
    "comment": "",
    "notice_period": ""
  }}
]

Return ONE object per resume, SAME ORDER.

INPUT:
{json.dumps(resumes)}
""".strip()


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

    BATCH_SIZE = 3

    for i in range(0, len(files), BATCH_SIZE):
        batch = files[i:i + BATCH_SIZE]

        groq_input = []
        file_context = []
        
        for f in batch:
            file_id = f.get("id")
            fname = f.get("name")
            mime = f.get("mimeType", "").lower()
            resume_url = f"https://drive.google.com/file/d/{file_id}/view"

            # Download file bytes from Google Drive
            try:
                file_bytes = _download_file_bytes(file_id)
            except HttpError:
                continue

            # Extract text locally
            try:
                resume_text = extract_text_from_bytes_by_mime(fname, file_bytes)
            except Exception:
                resume_text = ""

            # Skip junk resumes
            if not resume_text or len(resume_text) < 100:
                continue

            # Collect input for Groq (DO NOT PARSE HERE)
            groq_input.append({
                "text": resume_text,
                "resume_url": resume_url
            })

            file_context.append((f, resume_text, resume_url))
        # ===== GROQ EXTRACTION (BATCH LEVEL) =====
        if not groq_input:
            continue

        prompt = _build_groq_batch_prompt(groq_input)

        try:
            resp = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You extract resumes into structured JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            
            raw = resp.choices[0].message.content

            print("===== GROQ RAW START =====")
            print(raw)
            print("===== GROQ RAW END =====")

            if not raw:
                print("❌ Groq returned empty response")
                continue

            try:
                parsed_batch = json.loads(raw)
            except Exception:
                print("❌ Invalid JSON from Groq")
                print(raw)
                continue

        except Exception as e:
                print("Groq extraction failed:", e)
                continue


        # parsed_batch is a list of candidate dicts returned by Groq
        for c in parsed_batch:
            email = normalize_email(c.get("email", ""))
            name = normalize_name(c.get("candidate_name", ""))
            contact = normalize_phone(c.get("contact", ""))

            skillset = normalize_skilllist(c.get("skillset", ""))
            it_exp = c.get("it_experience", "")
            relevant_exp = c.get("relevant_experience", "")
            location = c.get("location", "")
            education = c.get("education", "")
            company = c.get("company", "")
            client = c.get("clients", "")
            comment = c.get("comment", "")
            notice_period = c.get("notice_period", "")
            resume_url = c.get("resumelinks", "")

            # Avoid duplicates (UNCHANGED LOGIC)
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

            # -------- EMBEDDING (INGESTION TIME) --------
            embed_parts = []
            if skillset:
                embed_parts.append(f"Skills: {skillset}")
            if it_exp:
                embed_parts.append(f"IT Experience: {it_exp}")
            if relevant_exp:
                embed_parts.append(f"Relevant Experience: {relevant_exp}")
            if location:
                embed_parts.append(f"Location: {location}")

            embedding = embed_text(" | ".join(embed_parts))

            candidate = Candidate(
                candidate_name=name,
                contact=contact,
                email=email,
                location=location,
                skillset=skillset,
                relevant_experience=relevant_exp,
                it_experience=it_exp,
                education=education,
                company=company,
                clients=client,
                resumelinks=resume_url,
                comment=comment,
                notice_period=notice_period,
                embedding=embedding,
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
                "Location": location,
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

    db.add(UserLog(user_id=admin.id, action=f"Resume extraction from folder={folder_id}, inserted={inserted}, duplicates={len(duplicates)}"))
    db.commit()

    return RedirectResponse(
        url=f"/admin?tab=uploadcsv&msg=Extraction+completed+({inserted}+rows)&duplicates={quote_plus(','.join(duplicates))}",
        status_code=302,
    )
