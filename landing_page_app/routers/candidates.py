# landing_page_app/routers/candidates.py
import re
from datetime import datetime
from typing import List, Optional, Tuple, Any, Dict

import requests
from fastapi import APIRouter, Depends, Body, HTTPException, Query, Request, Form
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from landing_page_app.database import get_db
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.models.jobs import Job
from landing_page_app.models.clients import Client

router = APIRouter(prefix="/candidates", tags=["Candidates"])
templates = Jinja2Templates(directory="landing_page_app/templates")


# -------------------------
# Experience parsing utils
# -------------------------
def parse_text_experience_to_months(text: Optional[Any]) -> Optional[int]:
    """
    Parse textual/numeric experience representations into integer months.
    Accepts plain numbers, floats, '4 years', '4 years 6 months', '6 months', etc.
    Returns months or None if cannot be parsed / blank.
    """
    if text is None:
        return None

    # numeric stored directly as years in DB or passed as numeric
    if isinstance(text, (int, float)):
        try:
            return int(round(float(text) * 12))
        except Exception:
            return None

    s = str(text).strip().lower()
    if s in ("", "n/a", "na", "none", "null"):
        return None

    years = 0.0
    months = 0

    # Find explicit year token (accept floats)
    m_year = re.search(r"(\d+(?:\.\d+)?)\s*(?:years|year|yrs|yr)\b", s)
    if m_year:
        try:
            years = float(m_year.group(1))
        except Exception:
            years = 0.0

    # Find months token
    m_month = re.search(r"(\d+)\s*(?:months|month|mos|mo)\b", s)
    if m_month:
        try:
            months = int(m_month.group(1))
        except Exception:
            months = 0

    # If no explicit 'years' token, maybe the string is just a number like "4" or "4.5"
    plain_num = None
    if m_year is None:
        plain_num = re.match(r"^\s*(\d+(?:\.\d+)?)\s*$", s)
        if plain_num:
            try:
                years = float(plain_num.group(1))
            except Exception:
                years = 0.0

    total_months = int(round(years * 12)) + months

    # if nothing was parsed at all, return None
    if total_months == 0 and m_year is None and m_month is None and not (plain_num is not None):
        return None

    return total_months


def parse_experience_filter_input(exp_input: str) -> Tuple[int, Optional[int]]:
    """
    Parse the user's filter input. Accepts:
      - "4" or "4 years" -> returns (48, None)
      - "4 years 6 months" -> returns (54, None)
      - "3-5" -> returns (36, 60)  (years range)
      - "2 years - 4 years 6 months" -> returns (24, 54)
    Returns (min_months, max_months or None).
    Raises ValueError if input can't be parsed.
    """
    if not exp_input or not exp_input.strip():
        raise ValueError("Empty experience filter")

    s = exp_input.strip()

    # Range form (using hyphen)
    if "-" in s:
        # split on first hyphen
        parts = [p.strip() for p in re.split(r"\s*-\s*", s, maxsplit=1) if p.strip()]
        if len(parts) != 2:
            raise ValueError("Experience range must be in 'min-max' form")
        left, right = parts
        left_months = parse_text_experience_to_months(left)
        right_months = parse_text_experience_to_months(right)
        if left_months is None or right_months is None:
            raise ValueError("Could not parse range endpoints")
        # Ensure min <= max
        if left_months <= right_months:
            return left_months, right_months
        else:
            return right_months, left_months

    # Single value
    single_months = parse_text_experience_to_months(s)
    if single_months is None:
        raise ValueError("Could not parse experience value")
    return single_months, None


# -------------------------
# JD fetching & keyword extraction
# -------------------------
_SKILL_TERMS = [
    # Common backend
    "python", "java", "c#", "c++", "go", "golang", "node.js", "nodejs", "php", "ruby",
    # Web/JS
    "javascript", "typescript", "react", "angular", "vue", "next.js", "nextjs",
    # Data/DB
    "sql", "mysql", "postgres", "postgresql", "mongodb", "oracle", "nosql", "snowflake", "redshift",
    # Cloud/DevOps
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "jenkins", "ci/cd",
    # Big Data / ML
    "hadoop", "spark", "pyspark", "hive", "airflow", "ml", "machine learning", "pytorch", "tensorflow",
    # Testing / QA
    "selenium", "cypress", "pytest", "junit",
    # Mobile
    "android", "ios", "flutter", "react native",
    # Other
    "rest", "restful", "graphql", "microservices", "linux", "git", "kafka"
]

_LOCATION_TERMS = [
    # India (common spellings)
    "bengaluru", "bangalore", "hyderabad", "pune", "mumbai", "navi mumbai", "thane",
    "chennai", "gurgaon", "gurugram", "noida", "delhi", "new delhi", "kolkata",
    # Global/common
    "remote", "anywhere", "work from home"
]


def _normalize_drive_link(drive_link: str) -> str:
    """
    Try to convert various Drive share URLs into a direct download/export URL.
    Supports:
      - https://drive.google.com/file/d/<ID>/view?usp=sharing
      - https://drive.google.com/open?id=<ID>
      - Google Docs URLs -> export as txt
    """
    s = drive_link.strip()
    # Google Docs document
    m_doc = re.search(r"https://docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", s)
    if m_doc:
        file_id = m_doc.group(1)
        return f"https://docs.google.com/document/d/{file_id}/export?format=txt"

    # Google Drive file share
    m_file = re.search(r"/d/([a-zA-Z0-9_-]+)", s)
    if m_file:
        file_id = m_file.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    # open?id=<id>
    m_open = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", s)
    if m_open:
        file_id = m_open.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    # If nothing matches, just return original (requests may still succeed)
    return s


def _extract_text_from_response(resp: requests.Response, source_url: str) -> str:
    """
    Best-effort conversion of response content into text.
    Tries to handle plain text, Google Docs export, PDF, DOCX. Falls back to utf-8 decode.
    """
    ctype = (resp.headers.get("Content-Type") or "").lower()

    # Plain text or Google Docs export returns text/plain
    if "text/plain" in ctype or source_url.endswith("format=txt"):
        try:
            return resp.text
        except Exception:
            pass

    # Try PDF (optional dependency)
    if "application/pdf" in ctype or source_url.lower().endswith(".pdf"):
        try:
            from io import BytesIO
            from PyPDF2 import PdfReader  # optional; if not installed, fallback
            reader = PdfReader(BytesIO(resp.content))
            pages = [p.extract_text() or "" for p in reader.pages]
            return "\n".join(pages).strip()
        except Exception:
            # fall through to generic decode
            pass

    # Try DOCX (optional dependency)
    if "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in ctype or source_url.lower().endswith(".docx"):
        try:
            from io import BytesIO
            import docx  # python-docx
            doc = docx.Document(BytesIO(resp.content))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            pass

    # Generic best-effort decode
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return resp.content.decode(enc, errors="ignore")
        except Exception:
            continue

    # Last resort
    return ""


def fetch_jd_text_from_drive(drive_link: str) -> str:
    """
    Fetch JD text content from a Google Drive/Docs link (best effort).
    Raises HTTPException on failure.
    """
    if not drive_link or not drive_link.strip():
        raise HTTPException(status_code=400, detail="Please provide a valid JD drive link.")

    url = _normalize_drive_link(drive_link)

    try:
        resp = requests.get(url, timeout=25)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch JD file: {e}")
    if resp.status_code != 200 or not resp.content:
        raise HTTPException(status_code=400, detail="Could not download/read JD file from the provided link.")

    text = _extract_text_from_response(resp, url).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Downloaded JD content is empty or unreadable.")
    return text


def _unique_preserve_order(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for s in seq:
        k = s.lower().strip()
        if k and k not in seen:
            out.append(s)
            seen.add(k)
    return out


def extract_keywords_from_jd(text: str) -> Dict[str, Optional[str]]:
    """
    Extract (skills, location, experience) from raw JD text.
    - Skills: intersection of configured SKILL_TERMS with JD text
    - Location: look for known locations or lines containing 'Location:'
    - Experience: pick explicit ranges like '3-5 years' or max single like '4 years'
    Returns strings suitable to pre-fill the search inputs.
    """
    lower = text.lower()

    # ---- Skills ----
    found_skills = []
    for term in _SKILL_TERMS:
        # exact term or sanitized '.' variants
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, lower):
            # standardize some names
            cleaned = term.replace(".js", "").replace("nodejs", "node.js").replace("nextjs", "next.js")
            if cleaned == "restful":
                cleaned = "REST"
            elif cleaned == "rest":
                cleaned = "REST"
            found_skills.append(cleaned)
    skills_out = ", ".join(_unique_preserve_order([s.upper() if s in {"AWS", "GCP"} else s.title() for s in found_skills])) or None

    # ---- Location ----
    # First try "Location: XYZ" style
    loc_candidate = None
    m_loc_line = re.search(r"location\s*:\s*([^\n\r,;]+)", lower)
    if m_loc_line:
        loc_candidate = m_loc_line.group(1).strip()
    else:
        locs_found = [loc for loc in _LOCATION_TERMS if re.search(r"\b" + re.escape(loc) + r"\b", lower)]
        if locs_found:
            loc_candidate = locs_found[0]

    if loc_candidate:
        # normalize some common spellings
        loc_norm = loc_candidate.replace("bengaluru", "Bangalore").replace("gurugram", "Gurgaon").title()
        if "remote" in loc_candidate:
            loc_norm = "Remote"
        location_out = loc_norm
    else:
        location_out = None

    # ---- Experience ----
    # Prefer explicit ranges like "3-5 years"
    m_range = re.search(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(?:years|year|yrs|yr)\b", lower)
    if m_range:
        left = m_range.group(1)
        right = m_range.group(2)
        experience_out = f"{left}-{right}"
    else:
        # Try "X years Y months", "X+ years", "at least X years"
        m_full = re.search(r"(\d+)\s*(?:years|year|yrs|yr)\s*(\d+)\s*(?:months|month|mos|mo)\b", lower)
        if m_full:
            experience_out = f"{m_full.group(1)} years {m_full.group(2)} months"
        else:
            m_plus = re.search(r"(?:at\s+least\s+|minimum\s+|min\s+)?(\d+(?:\.\d+)?)\s*\+?\s*(?:years|year|yrs|yr)\b", lower)
            if m_plus:
                experience_out = f"{m_plus.group(1)}"
            else:
                experience_out = None

    return {
        "skills": skills_out,
        "location": location_out,
        "experience": experience_out,
    }


# -------------------------
# --- Candidate Search ---
# -------------------------
@router.api_route("/search", methods=["GET", "POST"])
async def search_candidates(
    request: Request,
    skills: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    experience: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Render search page and results.
    - Accepts GET query params OR a POSTed HTML form (fields: skills, location, experience).
    - skills: comma separated
    - location: substring match
    - experience: supports 'X', 'X years', 'X years Y months', 'min-max' (years or full)
    """
    # If the client POSTed a form, override query values with form values
    if request.method and request.method.upper() == "POST":
        form = await request.form()
        # If the form contains values, override
        f_skills = form.get("skills")
        f_location = form.get("location")
        f_experience = form.get("experience")
        if f_skills is not None:
            skills = f_skills
        if f_location is not None:
            location = f_location
        if f_experience is not None:
            experience = f_experience

    # Build base query - exclude candidates already linked in CandidateJDMapping
    query = db.query(Candidate)
    # create subquery to exclude already linked candidate ids
    subq = db.query(CandidateJDMapping.candidate_id).distinct().subquery()
    query = query.filter(~Candidate.candidates_id.in_(subq))

    # Skills filter (SQL-side)
    if skills:
        # Accept comma-separated list; match each token in skillset (case-insensitive)
        skill_tokens = [t.strip().lower() for t in skills.split(",") if t.strip()]
        for tok in skill_tokens:
            # only match if candidate.skillset not null
            query = query.filter(func.lower(func.coalesce(Candidate.skillset, "")).like(f"%{tok}%"))

    # Location filter (SQL-side)
    if location:
        loc = location.strip().lower()
        query = query.filter(func.lower(func.coalesce(Candidate.location, "")).like(f"%{loc}%"))

    # Fetch candidate rows from DB (apply experience filter in Python for robustness)
    candidates = query.order_by(Candidate.candidates_id).all()

    # Experience filter parsing
    exp_min = None
    exp_max = None
    if experience:
        try:
            exp_min, exp_max = parse_experience_filter_input(experience)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid experience value. Use 'X years', 'X-Y' (e.g. 3-5), or 'X years Y months'."
            )

    results = []
    for c in candidates:
        # Apply experience filter if provided
        if experience:
            cand_months = parse_text_experience_to_months(c.it_experience)
            # if candidate experience can't be parsed -> treat as not matching
            if cand_months is None:
                continue
            if exp_min is not None and cand_months < exp_min:
                continue
            if exp_max is not None and cand_months > exp_max:
                continue

        # Get latest stage/status for candidate if any
        latest_status_row = (
            db.query(CandidateJDMapping.stage)
            .filter(CandidateJDMapping.candidate_id == c.candidates_id)
            .order_by(CandidateJDMapping.updated_at.desc())
            .limit(1)
            .first()
        )
        status_val = "Not Updated"
        if latest_status_row is not None:
            try:
                # If a tuple/row-like returned, extract first element
                if isinstance(latest_status_row, (list, tuple)):
                    status_val = latest_status_row[0]
                # SQLAlchemy scalar-like object: try attribute access
                elif hasattr(latest_status_row, "stage"):
                    status_val = getattr(latest_status_row, "stage")
                else:
                    status_val = str(latest_status_row)
            except Exception:
                status_val = str(latest_status_row)

        # Safely create mappings for both old/new template key names to avoid template breakages
        candidates_id_val = getattr(c, "candidates_id", None) or getattr(c, "id", None)
        skillset_val = getattr(c, "skillset", None) or getattr(c, "skills", None) or ""
        resumelink_val = getattr(c, "resumelinks", None) or getattr(c, "resume", None)

        results.append({
            # provide both common key names used across templates
            "id": candidates_id_val,
            "candidates_id": candidates_id_val,
            "candidate_name": getattr(c, "candidate_name", None),
            "email": getattr(c, "email", None),
            "contact": getattr(c, "contact", None),
            "location": getattr(c, "location", None),
            "skillset": skillset_val,
            "skills": skillset_val,
            "relevant_experience": getattr(c, "relevant_experience", None),
            "it_experience": getattr(c, "it_experience", None),
            "education": getattr(c, "education", None),
            "company": getattr(c, "company", None),
            "resumelinks": resumelink_val,
            "resume": resumelink_val,
            "clients": getattr(c, "clients", None),
            "notice_period": getattr(c, "notice_period", None),
            "comment": getattr(c, "comment", None),
            "status": status_val,
        })

    # Clients for dropdown
    clients = db.query(Client).order_by(Client.client_name).all()

    # Render template (keeps same template name as before)
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "results": results,
            "skills": skills,
            "location": location,
            "experience": experience,
            "clients": clients,
            # no advanced metadata here
        }
    )


# -------------------------
# --- Advanced Search (JD link → prefill filters) ---
# -------------------------
@router.post("/advanced-search")
async def advanced_search(
    request: Request,
    jd_drive_link: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Advanced search entry point.
    - Accepts a Google Drive/Docs link to a JD.
    - Fetches & parses the JD text.
    - Extracts (skills, location, experience).
    - Returns the normal search page with inputs pre-filled (no results yet) so the user can adjust and click Search.
    """
    jd_text = fetch_jd_text_from_drive(jd_drive_link)
    extracted = extract_keywords_from_jd(jd_text)

    # Only pre-fill; do not run a DB search yet (user can review/change and click Search)
    clients = db.query(Client).order_by(Client.client_name).all()
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "results": [],  # intentionally empty; user triggers search explicitly
            "skills": extracted.get("skills"),
            "location": extracted.get("location"),
            "experience": extracted.get("experience"),
            "clients": clients,
            "advanced_from_jd": True,  # optional flag if you want to show a small note in UI
        }
    )


# -------------------------
# --- Bulk Link to Job ---
# -------------------------
@router.post("/link-to-job")
def link_candidates_to_job(
    client_id: int = Body(...),
    jd_id: int = Body(...),
    candidate_ids: List[int] = Body(...),
    db: Session = Depends(get_db)
):
    """Link selected candidates to a specific job under a client."""
    if not candidate_ids:
        raise HTTPException(status_code=400, detail="No candidates selected.")

    client = db.query(Client).filter(Client.client_id == client_id).first()
    job = db.query(Job).filter(Job.job_id == jd_id, Job.client_id == client_id).first()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found for this client.")

    linked_count = 0
    for c_id in candidate_ids:
        mapping = db.query(CandidateJDMapping).filter(
            CandidateJDMapping.jd_id == jd_id,
            CandidateJDMapping.candidate_id == c_id
        ).first()

        if mapping:
            mapping.stage = "Linked"
            mapping.updated_at = datetime.utcnow()
        else:
            db.add(CandidateJDMapping(
                jd_id=jd_id,
                candidate_id=c_id,
                stage="Linked",
                updated_at=datetime.utcnow()
            ))
        linked_count += 1

    db.commit()
    return JSONResponse(content={"message": f"Linked {linked_count} candidates to JD '{job.job_title}' under client '{client.client_name}'."})


# -------------------------
# --- Shortlist Candidates ---
# -------------------------
@router.post("/{job_id}/shortlist")
def shortlist_candidates(
    job_id: int,
    candidate_ids: List[int] = Body(...),
    db: Session = Depends(get_db)
):
    """Shortlist candidates for a job."""
    if not candidate_ids:
        raise HTTPException(status_code=400, detail="No candidates provided.")

    for c_id in candidate_ids:
        mapping = db.query(CandidateJDMapping).filter(
            CandidateJDMapping.jd_id == job_id,
            CandidateJDMapping.candidate_id == c_id
        ).first()

        if mapping:
            mapping.stage = "Shortlisted"
            mapping.updated_at = datetime.utcnow()
        else:
            db.add(CandidateJDMapping(
                jd_id=job_id,
                candidate_id=c_id,
                stage="Shortlisted",
                updated_at=datetime.utcnow()
            ))

    db.commit()
    return JSONResponse(content={"message": f"{len(candidate_ids)} candidates shortlisted successfully."})


# -------------------------
# --- Get Jobs for Client ---
# -------------------------
@router.get("/jobs/{client_id}")
def get_jobs_for_client(client_id: int, db: Session = Depends(get_db)):
    """Fetch all jobs for a given client to populate JD dropdown."""
    jobs = db.query(Job).filter(Job.client_id == client_id).order_by(Job.job_title).all()
    return [{"jd_id": j.job_id, "title": j.job_title} for j in jobs]
