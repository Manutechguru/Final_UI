# landing_page_app/routers/candidates/search.py
from fastapi import APIRouter, Request, Query, Depends, Form, Body
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import re
from uuid import uuid4
import threading
import time

from landing_page_app.database import get_db
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping, STATUS_OPTIONS
from landing_page_app.models.clients import Client
from landing_page_app.models.managers import Manager
from landing_page_app.models.jobs import Job

# defensive import for helpers - if your search_utils provides these they'll be used
try:
    from landing_page_app.routers.utils.search_utils import (
        parse_experience_filter_input,
        parse_text_experience_to_months,
        extract_jd_features,
        ai_match_jd_with_resumes,
        fetch_text_from_url,
    )
except Exception:
    # minimal fallbacks so server doesn't crash while you iterate
    def parse_experience_filter_input(x): return (None, None)
    def extract_jd_features(x): return {"skills": "", "experience": "", "location": "", "summary": ""}
    def ai_match_jd_with_resumes(jd_text, candidates): return []
    def fetch_text_from_url(url): return url or ""
    def parse_text_experience_to_months(x):
        return 0

from landing_page_app.models.user import User
from landing_page_app.deps import get_current_user

templates = Jinja2Templates(directory="landing_page_app/templates")
router = APIRouter(prefix="/candidates", tags=["candidates"])
logger = logging.getLogger(__name__)

# -------------------------
# Small helpers to tolerate schema differences
# -------------------------
def _first_attr(obj, names: List[str], default=None):
    """Return first existing attribute value on obj for any name in names."""
    for n in names:
        if hasattr(obj, n):
            try:
                return getattr(obj, n)
            except Exception:
                continue
    return default

def _first_column(cls, names: List[str]):
    """Return first column attribute on SQLAlchemy model class that exists, or None."""
    for n in names:
        if hasattr(cls, n):
            return getattr(cls, n)
    return None


# -------------------------
# Active-state helpers (DB & Python) for dropdown filtering
# -------------------------
_ACTIVE_FIELD_NAMES = [
    "status", "is_active", "active", "enabled", "is_enabled", "status_id", "state"
]

def _py_obj_is_active(obj) -> bool:
    """
    Python-side check for whether a model instance appears active.
    Looks for common fields (status, is_active etc.) and handles strings, bools, ints.
    Defaults to True if no known field exists to avoid accidental hiding.
    """
    for name in _ACTIVE_FIELD_NAMES:
        if hasattr(obj, name):
            try:
                val = getattr(obj, name)
            except Exception:
                continue
            if val is None:
                return False
            if isinstance(val, bool):
                return bool(val)
            if isinstance(val, (int, float)):
                try:
                    return int(val) == 1
                except Exception:
                    pass
            s = str(val).strip().lower()
            if not s:
                return False
            if s in ("1", "true", "yes", "active", "enabled", "on"):
                return True
            if s in ("0", "false", "no", "inactive", "off"):
                return False
            if "active" in s:
                return True
            return False
    # If no active-like field found, default to True (do not hide)
    return True

def _apply_active_filter_to_query(q, cls):
    """
    Apply an SQLAlchemy filter to the query to only include 'active' rows if the model
    exposes a known status/is_active column. If no known column exists, return the query unchanged.
    """
    # Prefer textual 'status' == 'active'
    if hasattr(cls, "status"):
        try:
            return q.filter(getattr(cls, "status") == "active")
        except Exception:
            pass
    # Then fallback to boolean-like fields
    for name in ("is_active", "active", "enabled", "is_enabled"):
        if hasattr(cls, name):
            try:
                return q.filter(getattr(cls, name) == True)
            except Exception:
                pass
    # nothing applied
    return q

def _get_active_clients(db: Session) -> List:
    """
    Return clients ordered by name but filtered to active clients when possible.
    """
    try:
        q = db.query(Client).order_by(getattr(Client, "client_name", "id"))
        q = _apply_active_filter_to_query(q, Client)
        return q.all()
    except Exception:
        # fallback: load all and filter in python
        try:
            rows = db.query(Client).order_by(getattr(Client, "client_name", "id")).all()
            return [r for r in rows if _py_obj_is_active(r)]
        except Exception:
            return []
# Safe mapping builders
def _vendor_dict_from_manager(mgr):
    return {
        "vendor_id": _first_attr(mgr, ["manager_id", "id", "vendor_id", "managerId"]),
        "vendor_name": _first_attr(mgr, ["manager_name", "name", "vendor_name", "managerName"])
    }

def _job_dict_from_job(job):
    return {
        "job_id": _first_attr(job, ["job_id", "id", "jobId"]),
        "job_title": _first_attr(job, ["job_title", "title", "jobTitle"])
    }

# shape candidate for templates (keeps keys templates use)
def _candidate_to_row(cand: Candidate, mapping: Optional[CandidateJDMapping] = None) -> Dict[str, Any]:
    ai_score = getattr(cand, "ai_score", None) or getattr(cand, "score", None)
    return {
        "candidates_id": getattr(cand, "candidates_id", None),
        "candidate_name": getattr(cand, "candidate_name", None),
        "email": getattr(cand, "email", None),
        "contact": getattr(cand, "contact", None),
        "location": getattr(cand, "location", None),
        "skillset": getattr(cand, "skillset", "") or "",
        "it_experience": getattr(cand, "it_experience", None),
        "relevant_experience": getattr(cand, "relevant_experience", None),
        "education": getattr(cand, "education", None),
        "company": getattr(cand, "company", None),
        "resumelinks": getattr(cand, "resumelinks", None),
        "notice_period": getattr(cand, "notice_period", None),
        "comment": getattr(cand, "comment", None),
        "clients": getattr(cand, "clients", None),
        "recruitment_notes": getattr(cand, "recruitment_notes", "") or "",
        "recruiter_notes": getattr(cand, "recruitment_notes", "") or "",
        "ai_score": ai_score,
        "ai_explanation": getattr(cand, "ai_explanation", "") or "",
        "score": ai_score,
        "is_linked": bool(mapping) if mapping else False,
        "mapping_id": getattr(mapping, "id", None) or getattr(mapping, "mapping_id", None) if mapping else None,
        "mapping_jd_id": getattr(mapping, "jd_id", None) if mapping else None,
    }

# -------------------------
# Strict token-level location & experience helpers (ADDED)
# -------------------------
def _normalize_tokens(s: Optional[str]) -> List[str]:
    if not s:
        return []
    parts = re.split(r"[,\|;/\-]+|\s+", str(s).lower())
    return [p.strip() for p in parts if p and p.strip()]

def _location_matches(candidate_location: Optional[str], query_location: Optional[str]) -> bool:
    """Strict token-level location match.
    - if query_location empty -> True (no filtering)
    - if candidate_location empty -> False (candidate lacks location)
    - require every token in query_location to be exactly present in candidate tokens.
    """
    if not query_location or not str(query_location).strip():
        return True
    if not candidate_location or not str(candidate_location).strip():
        return False
    q_tokens = _normalize_tokens(query_location)
    c_tokens = _normalize_tokens(candidate_location)
    for q in q_tokens:
        if not any(q == c for c in c_tokens):
            return False
    return True

def _candidate_experience_months(cand) -> int:
    """Return candidate's best-parsed experience in months (max of common fields)."""
    vals = []
    for attr in ["relevant_experience", "it_experience", "experience"]:
        try:
            v = getattr(cand, attr, None) or ""
            if v:
                try:
                    vals.append(parse_text_experience_to_months(v))
                except Exception:
                    pass
        except Exception:
            pass
    return max(vals) if vals else 0

def _filter_candidates_by_experience(candidates: List, min_months: Optional[int], max_months: Optional[int]) -> List:
    out = []
    for c in candidates:
        cand_months = _candidate_experience_months(c)
        if min_months is not None:
            if cand_months == 0:
                # candidate lacks parsable experience -> exclude when min requested
                continue
            if cand_months < min_months:
                continue
        if max_months is not None and cand_months > max_months:
            continue
        out.append(c)
    return out


# -------------------------
# Manual search (UI)
# -------------------------
@router.get("/search")
async def search(request: Request,
                 skills: Optional[str] = Query(None),
                 location: Optional[str] = Query(None),
                 experience: Optional[str] = Query(None),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):

    min_m, max_m = None, None

    # --- EARLY RETURN (Reset/initial load) ---
    # If no manual filters are provided, render empty results so Reset clears the table.
    if not ((skills and skills.strip()) or (location and location.strip()) or (experience and experience.strip())):
        clients = _get_active_clients(db)
        return templates.TemplateResponse("search.html", {
            "request": request,
            "results": [],
            "skills": skills or "",
            "location": location or "",
            "experience": experience or "",
            "clients": clients,
            "user": user,
        })

    # 1) Start from all candidates
    q = db.query(Candidate)

    # skills filter
    if skills:
        tokens = [t.strip() for t in skills.split(",") if t.strip()]
        if tokens:
            filters = [func.lower(func.coalesce(Candidate.skillset, "")).like(f"%{t.lower()}%") for t in tokens]
            q = q.filter(or_(*filters))

    # location prefilter
    if location:
        q = q.filter(func.lower(func.coalesce(Candidate.location, "")).like(f"%{location.strip().lower()}%"))

    # fetch candidates (without wrong LIKE on years)
    candidates = q.order_by(func.coalesce(Candidate.candidates_id, 0).desc()).limit(500).all()

    # strict location match
    if location and str(location).strip():
        candidates = [c for c in candidates if _location_matches(getattr(c, 'location', '') or '', location)]

    # experience filter using months
    if experience and str(experience).strip():
        try:
            min_m, max_m = parse_experience_filter_input(experience)
        except Exception:
            min_m, max_m = None, None

    if min_m is not None or max_m is not None:
        candidates = _filter_candidates_by_experience(candidates, min_m, max_m)

    final_list = candidates


    
    # 4) Map to rows for template (attach mapping metadata -> is_linked, existing_jd_ids, mapping_display)
    from collections import defaultdict
    cand_ids = [getattr(c, "candidates_id", None) for c in final_list if getattr(c, "candidates_id", None) is not None]
    mappings_by_cid = defaultdict(list)
    mapping_info_map = {}

    if cand_ids:
        try:
            rows = db.query(CandidateJDMapping).filter(CandidateJDMapping.candidate_id.in_(cand_ids)).all()
            for r in rows:
                cid_key = getattr(r, "candidate_id", None)
                if cid_key is not None:
                    mappings_by_cid[cid_key].append(r)
        except Exception:
            mappings_by_cid = defaultdict(list)

    # build job/manager/client lookup maps so we can show "Client > Vendor > Job"
    try:
        all_job_ids = set()
        for lst in mappings_by_cid.values():
            for m in lst:
                jid = getattr(m, "jd_id", None)
                if jid is not None:
                    try:
                        all_job_ids.add(int(jid))
                    except Exception:
                        all_job_ids.add(jid)

        job_map = {}
        if all_job_ids:
            id_col = _first_column(Job, ["job_id", "id", "jobId"])
            if id_col is not None:
                try:
                    jobs = db.query(Job).filter(id_col.in_(list(all_job_ids))).all()
                except Exception:
                    jobs = []
                for j in jobs:
                    try:
                        # Use the job id columns as the lookup key (job_id / id / jobId).
                        job_id_val = _first_attr(j, ["job_id", "id", "jobId"])
                        job_key = int(job_id_val) if isinstance(job_id_val, (int, str)) and str(job_id_val).isdigit() else job_id_val
                        job_map[job_key] = j
                    except Exception:
                        continue

        # collect manager (vendor) ids from jobs
        manager_ids = set()
        for j in job_map.values():
            mid = _first_attr(j, ["manager_id", "managerId", "manager", "vendor_id"])
            if mid is not None:
                try:
                    manager_ids.add(int(mid))
                except Exception:
                    manager_ids.add(mid)

        manager_map = {}
        if manager_ids:
            mgr_col = _first_column(Manager, ["manager_id", "id", "vendor_id", "managerId"])
            if mgr_col is not None:
                try:
                    managers = db.query(Manager).filter(mgr_col.in_(list(manager_ids))).all()
                except Exception:
                    managers = []
                for m in managers:
                    try:
                        mid_val = _first_attr(m, ["manager_id", "id", "vendor_id", "managerId"])
                        key = int(mid_val) if isinstance(mid_val, (int, str)) and str(mid_val).isdigit() else mid_val
                        manager_map[key] = m
                    except Exception:
                        continue

        # collect client ids from managers
        client_ids = set()
        for m in manager_map.values():
            cid = _first_attr(m, ["client_id", "clientId", "client"])
            if cid is not None:
                try:
                    client_ids.add(int(cid))
                except Exception:
                    client_ids.add(cid)

        client_map = {}
        if client_ids:
            ccol = _first_column(Client, ["client_id", "id", "clientId"])
            if ccol is not None:
                try:
                    clients = db.query(Client).filter(ccol.in_(list(client_ids))).all()
                except Exception:
                    clients = []
                for cobj in clients:
                    try:
                        cid_val = _first_attr(cobj, ["client_id", "id", "clientId"])
                        key = int(cid_val) if isinstance(cid_val, (int, str)) and str(cid_val).isdigit() else cid_val
                        client_map[key] = cobj
                    except Exception:
                        continue

        # now build mapping_info_map per candidate id
        for cid_key, lst in mappings_by_cid.items():
            info_list = []
            for m in lst:
                jid = getattr(m, "jd_id", None)
                job = None
                job_title = ""
                vendor_name = ""
                client_name = ""
                try:
                    jkey = int(jid) if isinstance(jid, (int, str)) and str(jid).isdigit() else jid
                    job = job_map.get(jkey)
                except Exception:
                    job = None
                if job:
                    job_title = _first_attr(job, ["job_title", "title", "jobTitle"]) or ""
                    mid = _first_attr(job, ["manager_id", "managerId", "manager", "vendor_id"])
                    try:
                        mkey = int(mid) if isinstance(mid, (int, str)) and str(mid).isdigit() else mid
                    except Exception:
                        mkey = mid
                    manager = manager_map.get(mkey)
                    if manager:
                        vendor_name = _first_attr(manager, ["manager_name", "name", "vendor_name", "managerName"]) or ""
                        client_id_ref = _first_attr(manager, ["client_id", "clientId", "client"])
                        try:
                            ck = int(client_id_ref) if isinstance(client_id_ref, (int, str)) and str(client_id_ref).isdigit() else client_id_ref
                        except Exception:
                            ck = client_id_ref
                        client_obj = client_map.get(ck)
                        if client_obj:
                            client_name = _first_attr(client_obj, ["client_name", "name", "clientName"]) or ""
                info_list.append({
                    "jd_id": jid,
                    "job_title": job_title or "",
                    "vendor_name": vendor_name or "",
                    "client_name": client_name or "",
                    "mapping_id": getattr(m, "id", None) or getattr(m, "mapping_id", None)
                })
            mapping_info_map[cid_key] = info_list

    except Exception:
        mapping_info_map = {}

    # produce final result rows (attach mapping metadata)
    results = []
    for c in final_list:
        mapping_list = mappings_by_cid.get(getattr(c, "candidates_id", None)) or []
        base_map = mapping_list[0] if mapping_list else None
        row = _candidate_to_row(c, base_map)
        cid_val = getattr(c, "candidates_id", None)
        info = mapping_info_map.get(cid_val, [])
        row["is_linked"] = bool(info)
        row["existing_jd_ids"] = [i.get("jd_id") for i in info]
        
        try:
            row["mapping_display"] = " | ".join([ (f"{(i.get('client_name') or '').strip() + (' > ' if (i.get('client_name') or '') else '')}{(i.get('vendor_name') or '')}{(' > ' if (i.get('vendor_name') or '') else '')}{(i.get('job_title') or '')}").strip(" > ") for i in info ]) or ""
        except Exception:
            row["mapping_display"] = ""

            row["mapping_display"] = ""
        results.append(row)


    clients = _get_active_clients(db)
    return templates.TemplateResponse("search.html", {
        "request": request,
        "results": results,
        "skills": skills or "",
        "location": location or "",
        "experience": experience or "",
        "clients": clients,
    })

# -------------------------
# Manual AI endpoint (AJAX)
# -------------------------
# -------------------------
# Advanced: Parse JD link and AI-match (UI)
# -------------------------
# -------------------------
# Cascading dropdown endpoints (client -> vendors -> jobs)
# -------------------------

@router.get("/get-vendors/{client_id}")
async def get_vendors_by_client(client_id: int, db: Session = Depends(get_db)):
    """
    Robust vendor lookup: tolerant to different Manager model attribute names.
    Returns: [{"vendor_id":..., "vendor_name":...}, ...]
    """
    client_cols = ["client_id", "client", "clientId", "clientid"]
    col = _first_column(Manager, client_cols)
    vendors = []
    try:
        q = db.query(Manager)
        if col is not None:
            q = q.filter(col == client_id)
        # apply SQL-level active filter when possible
        q = _apply_active_filter_to_query(q, Manager)
        vendors = q.all()
    except Exception:
        # fallback: fetch all and filter in python (also enforce active)
        try:
            rows = db.query(Manager).all()
            for r in rows:
                if str(_first_attr(r, client_cols) or "") != str(client_id):
                    continue
                if _py_obj_is_active(r):
                    vendors.append(r)
        except Exception:
            vendors = []

    out = []
    for v in vendors:
        vid = _first_attr(v, ["manager_id", "id", "vendor_id", "managerId"])
        vname = _first_attr(v, ["manager_name", "name", "vendor_name", "managerName"])
        if vid is None:
            # skip corrupted rows
            continue
        out.append({"vendor_id": vid, "vendor_name": vname or ""})
    return JSONResponse(out)


@router.get("/get-jobs/{vendor_id}")
async def get_jds_by_vendor(vendor_id: int, db: Session = Depends(get_db)):
    """
    Robust jobs lookup tolerant to different Job model field names.
    Returns: [{"job_id":..., "job_title":...}, ...]
    """
    manager_cols = ["manager_id", "managerId", "manager", "vendor_id"]
    col = _first_column(Job, manager_cols)
    jobs = []
    try:
        q = db.query(Job)
        if col is not None:
            q = q.filter(col == vendor_id)
        # apply SQL-level active filter when possible
        q = _apply_active_filter_to_query(q, Job)
        jobs = q.all()
    except Exception:
        # fallback: fetch all and filter in python (also enforce active)
        try:
            rows = db.query(Job).all()
            for j in rows:
                if str(_first_attr(j, manager_cols) or "") != str(vendor_id):
                    continue
                if _py_obj_is_active(j):
                    jobs.append(j)
        except Exception:
            jobs = []

    out = []
    for j in jobs:
        jid = _first_attr(j, ["job_id", "id", "jobId"])
        jtitle = _first_attr(j, ["job_title", "title", "jobTitle"])
        if jid is None:
            continue
        out.append({"job_id": jid, "job_title": jtitle or ""})
    return JSONResponse(out)

@router.get("/get-mapped-candidates/{job_id}")
async def get_mapped_candidates(job_id: int, db: Session = Depends(get_db)):
    try:
        rows = db.query(CandidateJDMapping).filter(CandidateJDMapping.jd_id == job_id).all()
    except Exception:
        rows = []
    out = []
    for r in rows:
        out.append({
            "mapping_id": getattr(r, "id", None) or getattr(r, "mapping_id", None),
            "candidate_id": getattr(r, "candidate_id", None),
            "ai_score": getattr(r, "ai_score", None),
            "created_at": getattr(r, "created_at", None),
            "recruitment_notes": getattr(r, "recruitment_notes", None) or "",
            "stage": getattr(r, "stage", None) or "",
        })
    return JSONResponse(out)

# -------------------------
# Toggle link/unlink mapping (AJAX)
# -------------------------
@router.post("/toggle-link")
async def toggle_candidate_link(payload: dict = Body(...), db: Session = Depends(get_db)):
    candidate_id = payload.get("candidate_id")
    job_id = payload.get("job_id")
    linked = bool(payload.get("linked", False))
    ai_score = payload.get("ai_score", None)

    if not candidate_id or not job_id:
        return JSONResponse({"message": "candidate_id and job_id required"}, status_code=400)
    try:
        if linked:
            mapping = db.query(CandidateJDMapping).filter(
                CandidateJDMapping.candidate_id == candidate_id,
                CandidateJDMapping.jd_id == job_id
            ).first()
            if mapping:
                # update ai_score if present
                try:
                    if ai_score is not None:
                        setattr(mapping, "ai_score", ai_score)
                        db.add(mapping); db.commit()
                except Exception:
                    db.rollback()
                return JSONResponse({"message": "Updated mapping", "mapping_id": getattr(mapping, "id", None) or getattr(mapping, "mapping_id", None)})
            # create mapping safely (do not pass unknown kwargs)
            new_map = CandidateJDMapping(candidate_id=candidate_id, jd_id=job_id)
            try:
                if ai_score is not None:
                    setattr(new_map, "ai_score", int(ai_score))
            except Exception:
                pass
            try:
                db.add(new_map); db.commit()
            except Exception:
                db.rollback()
            return JSONResponse({"message": "Linked candidate", "mapping_id": getattr(new_map, "id", None) or getattr(new_map, "mapping_id", None)})
        else:
            deleted = False
            rows = db.query(CandidateJDMapping).filter(
                CandidateJDMapping.candidate_id == candidate_id,
                CandidateJDMapping.jd_id == job_id
            ).all()
            for r in rows:
                try:
                    db.delete(r)
                    deleted = True
                except Exception:
                    pass
        try:
            db.commit()
        except Exception:
            db.rollback()
            return JSONResponse({"message": "Unlinked candidate", "deleted": deleted})
    except Exception as exc:
        db.rollback()
        return JSONResponse({"message": f"Toggle failed: {exc}"}, status_code=500)

@router.post("/update-note")
async def update_recruitment_note(payload: dict = Body(...), db: Session = Depends(get_db)):
    candidate_id = payload.get("candidate_id")
    job_id = payload.get("job_id", 0)
    note = payload.get("note", "") or ""

    if not candidate_id:
        return JSONResponse({"message": "Provide candidate_id"}, status_code=400)

    cand = db.query(Candidate).filter(Candidate.candidates_id == int(candidate_id)).first()
    if not cand:
        return JSONResponse({"message": "Candidate not found"}, status_code=404)

    try:
        # primary target: candidates.recruitment_notes
        try:
            setattr(cand, "recruitment_notes", note)
        except Exception:
            # alternate names
            try:
                setattr(cand, "recruiter_notes", note)
            except Exception:
                pass
        db.add(cand); db.commit()
    except Exception as exc:
        db.rollback()
        return JSONResponse({"message": f"Failed to save note: {exc}"}, status_code=500)

    mapping_id = None
    # if job_id passed, ensure mapping exists and return its id (front-end expects this to toggle checkbox)
    if job_id and int(job_id) > 0:
        try:
            existing = db.query(CandidateJDMapping).filter(CandidateJDMapping.candidate_id == int(candidate_id), CandidateJDMapping.jd_id == int(job_id)).first()
            if existing:
                mapping_id = getattr(existing, "id", None) or getattr(existing, "mapping_id", None)
            else:
                m = CandidateJDMapping(candidate_id=int(candidate_id), jd_id=int(job_id))
                try:
                    db.add(m); db.commit()
                    mapping_id = getattr(m, "id", None) or getattr(m, "mapping_id", None)
                except Exception:
                    db.rollback()
        except Exception:
            mapping_id = None

    return JSONResponse({"mapping_id": mapping_id})

# -------------------------
# STATIC 'Recently linked' / shortlist redirect (accepts optional highlight query param)
# -------------------------
@router.get("/shortlisted")
async def shortlisted_page(request: Request, highlight: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """
    Redirect to the JD page that most recently had a candidate linked.
    Accepts optional 'highlight' query parameter (comma separated IDs) from the UI link.
    """
    try:
        latest = db.query(CandidateJDMapping).order_by(getattr(CandidateJDMapping, "created_at", CandidateJDMapping.id).desc()).first()
        if latest and getattr(latest, "jd_id", None):
            # Keep the highlight param if present when redirecting to JD page
            url = f"/candidates/jd/{getattr(latest, 'jd_id')}"
            if highlight:
                url = url + f"?highlight={highlight}"
            return RedirectResponse(url=url)
    except Exception:
        pass
    return RedirectResponse(url="/candidates/search")

# -------------------------
# JD page to show linked candidates (renders jd_candidates.html used by frontend)
# -------------------------
@router.get("/jd/{jd_id}")
async def jd_candidates(request: Request, jd_id: int, db: Session = Depends(get_db)):
    try:
        mappings = db.query(CandidateJDMapping).filter(CandidateJDMapping.jd_id == jd_id).all()
    except Exception:
        mappings = []

    candidate_ids = [getattr(m, "candidate_id", None) for m in mappings if getattr(m, "candidate_id", None) is not None]
    candidates = []
    if candidate_ids:
        candidates = db.query(Candidate).filter(Candidate.candidates_id.in_(candidate_ids)).all()

    results = []
    for m in mappings:
        cid = getattr(m, "candidate_id", None)
        c = next((x for x in candidates if getattr(x, "candidates_id", None) == cid), None)
        if not c:
            results.append({
                "candidate_id": cid,
                "candidate_name": _first_attr(m, ["candidate_name","name"], ""),
                "email": _first_attr(m, ["email"], ""),
                "contact": _first_attr(m, ["contact"], ""),
                "skillset": _first_attr(m, ["skillset"], ""),
                "location": _first_attr(m, ["location"], ""),
                "it_experience": _first_attr(m, ["it_experience","experience"], ""),
                "education": _first_attr(m, ["education"], ""),
                "company": _first_attr(m, ["company"], ""),
                "resumelinks": _first_attr(m, ["resumelinks"], ""),
                "clients": _first_attr(m, ["clients"], ""),
                "notice_period": _first_attr(m, ["notice_period"], ""),
                "comment": _first_attr(m, ["comment"], ""),
                "recruiter_notes": _first_attr(m, ["recruiter_notes","recruitment_notes"], ""),
                "stage": _first_attr(m, ["stage"], ""),
                "ai_score": _first_attr(m, ["ai_score"], None),
            })
            continue

        row = {
            "candidate_id": getattr(c, "candidates_id", None),
            "candidate_name": getattr(c, "candidate_name", None),
            "email": getattr(c, "email", None),
            "contact": getattr(c, "contact", None),
            "skillset": getattr(c, "skillset", None),
            "location": getattr(c, "location", None),
            "it_experience": getattr(c, "it_experience", None),
            "relevant_experience": getattr(c, "relevant_experience", None),
            "education": getattr(c, "education", None),
            "company": getattr(c, "company", None),
            "resumelinks": getattr(c, "resumelinks", None),
            "clients": getattr(c, "clients", None),
            "notice_period": getattr(c, "notice_period", None),
            "comment": getattr(c, "comment", None),
            "recruiter_notes": getattr(c, "recruitment_notes", "") or "",
            "stage": getattr(m, "stage", None) or "",
            "ai_score": getattr(m, "ai_score", None) or getattr(c, "ai_score", None) or None,
        }
        results.append(row)

    try:
        status_options = STATUS_OPTIONS if STATUS_OPTIONS else []
    except Exception:
        status_options = ["Sourced", "Shortlisted", "Interview", "Offered", "Hired", "Rejected"]

    return templates.TemplateResponse("jd_candidates.html", {
        "request": request,
        "jd_id": jd_id,
        "candidates": results,
        "status_options": status_options,
    })

# -------------------------
# AI explanation & reset endpoints (AJAX)
# -------------------------
@router.get("/ai-explanation/{candidate_id}")
async def ai_explanation(candidate_id: int, db: Session = Depends(get_db)):
    cand = db.query(Candidate).filter(Candidate.candidates_id == candidate_id).first()
    if not cand:
        return JSONResponse({}, status_code=404)
    return JSONResponse({"ai_score": getattr(cand, "ai_score", None), "explanation": getattr(cand, "ai_explanation", "") or ""})

@router.post("/ai-reset")
async def ai_reset(payload: dict = Body(...), db: Session = Depends(get_db)):
    candidate_id = payload.get("candidate_id")
    if not candidate_id:
        return JSONResponse({"message": "Provide candidate_id"}, status_code=400)
    cand = db.query(Candidate).filter(Candidate.candidates_id == int(candidate_id)).first()
    if not cand:
        return JSONResponse({"message": "Candidate not found."}, status_code=404)
    try:
        try: setattr(cand, "ai_score", None)
        except Exception: pass
        try: setattr(cand, "ai_explanation", "")
        except Exception: pass
        db.add(cand); db.commit()
        return JSONResponse({"message": "AI score reset."})
    except Exception as exc:
        db.rollback()
        return JSONResponse({"message": f"Failed to reset: {exc}"}, status_code=500)

@router.post("/link-to-jd")
async def link_selected_candidates(payload: dict = Body(...), db: Session = Depends(get_db)):
    jd_id = payload.get("jd_id")
    candidate_ids = payload.get("candidate_id", []) or []
    ai_scores = payload.get("ai_scores", {}) or {}
    if not jd_id or not candidate_ids:
        return JSONResponse({"message": "jd_id and candidate_id list required"}, status_code=400)
    added = 0; updated = 0
    for cid in candidate_ids:
        try:
            exists = db.query(CandidateJDMapping).filter(CandidateJDMapping.candidate_id == cid, CandidateJDMapping.jd_id == jd_id).first()
            score_val = ai_scores.get(str(cid)) or ai_scores.get(int(cid))
            if exists:
                try:
                    if score_val is not None: setattr(exists, "ai_score", score_val)
                    db.add(exists); updated += 1
                except Exception: pass
            else:
                m = CandidateJDMapping(candidate_id=cid, jd_id=jd_id)
                try:
                    if score_val is not None: setattr(m, "ai_score", score_val)
                except Exception: pass
                try: db.add(m); added += 1
                except Exception: db.rollback()
        except Exception:
            continue
    try:
        db.commit()
    except Exception:
        db.rollback()
    return JSONResponse({"message": f"Linked {len(candidate_ids)} candidates (created={added} updated={updated})."})

# -------------------------
# Background AI job support (optional)
# -------------------------
AI_JOBS: Dict[str, Dict[str, Any]] = {}

def _start_ai_worker(jd_link: str, job_id: str):
    """Background worker that scores candidates in the background and writes results to AI_JOBS[job_id]."""
    db = None
    try:
        db = get_db().connect()
    except Exception:
        # fallback: no DB connection for worker
        return

    try:
        jd_text = fetch_text_from_url(jd_link) if callable(fetch_text_from_url) else jd_link
        if not jd_text:
            jd_text = jd_link
    except Exception:
        jd_text = jd_link

    # extract prefill
    try:
        extracted = extract_jd_features(jd_text) or {}
    except Exception:
        extracted = {}
    pre_skills = extracted.get("skills", "") or ""
    pre_location = extracted.get("location", "") or ""
    pre_experience = extracted.get("experience", "") or ""

    # initialize experience bounds
    min_m, max_m = None, None

    AI_JOBS[job_id]["prefill"] = {"skills": pre_skills, "location": pre_location, "experience": pre_experience}

    # Score candidates in batches using existing helper
    # PREFILTER candidates by extracted fields (only if those fields were actually extracted)
    q = db.query(Candidate)
    if pre_skills:
        tokens = [t.strip() for t in pre_skills.split(',') if t.strip()]
        if tokens:
            filters = [func.lower(func.coalesce(Candidate.skillset, '')).like(f"%{t.lower()}%") for t in tokens]
            q = q.filter(or_(*filters))
    if pre_location:
        q = q.filter(func.lower(func.coalesce(Candidate.location, '')).like(f"%{pre_location.strip().lower()}%"))

    all_candidates = q.order_by(getattr(Candidate, 'candidates_id', Candidate)).all()

    # Enforce strict token-level location & strict experience filtering (post-prefilter)
    if pre_location:
        all_candidates = [c for c in all_candidates if _location_matches(getattr(c, 'location', '') or '', pre_location)]

    if pre_experience and str(pre_experience).strip():
        try:
            min_m, max_m = parse_experience_filter_input(pre_experience)
        except Exception:
            min_m, max_m = None, None
        if min_m is not None:
            all_candidates = _filter_candidates_by_experience(all_candidates, min_m, max_m)

    total = max(1, len(all_candidates))
    batch = 10
    matched_ids = set()
    score_map = {}
    expl_map = {}

    for i in range(0, len(all_candidates), batch):
        slice_batch = all_candidates[i:i+batch]
        try:
            scored = ai_match_jd_with_resumes(jd_text, slice_batch)
        except Exception as exc:
            logger.exception("ai_match_jd_with_resumes failed in worker: %s", exc)
            scored = []

        for item in (scored or []):
            cid = item.get("candidate_id") or item.get("candidates_id") or item.get("id")
            score = item.get("ai_score") or item.get("score") or 0
            expl = item.get("explanation") or item.get("reasons") or item.get("ai_explanation") or ""
            if cid:
                try:
                    cid = int(cid)
                    matched_ids.add(cid)
                    score_map[cid] = int(score)
                    if expl:
                        expl_map[cid] = expl
                except Exception:
                    continue
        AI_JOBS[job_id]["progress"] = int(min(100, (i+batch) / total * 100))
        AI_JOBS[job_id]["matched_ids"] = list(matched_ids)
        AI_JOBS[job_id]["result_count"] = len(matched_ids)

    # store result_count and matched_ids
    AI_JOBS[job_id]["status"] = "done"
    AI_JOBS[job_id]["progress"] = 100
    AI_JOBS[job_id]["matched_ids"] = list(matched_ids)
    AI_JOBS[job_id]["result_count"] = len(matched_ids)
    try:
        db.commit()
    except Exception:
        db.rollback()
    finally:
        try:
            db.close()
        except Exception:
            pass

@router.post("/ai-job")
async def start_ai_job(request: Request):
    """
    Start a background AI evaluation job for the provided JD link.
    Accepts either JSON { jd_drive_link: "." } or form data jd_drive_link=.
    Returns: {"job_id": "<uuid>"}
    """
    data = {}
    try:
        data = await request.json()
    except Exception:
        try:
            form = await request.form()
            data = dict(form)
        except Exception:
            data = {}

    jd_drive_link = data.get("jd_drive_link") or data.get("jd_link") or data.get("jdDriveLink") or ""
    if not jd_drive_link:
        return JSONResponse({"message": "jd_drive_link is required"}, status_code=400)

    job_id = str(uuid4())
    AI_JOBS[job_id] = {"status": "pending", "progress": 0, "result_count": 0, "prefill": {}, "error": None, "matched_ids": []}

    # start background thread
    thread = threading.Thread(target=_start_ai_worker, args=(jd_drive_link, job_id), daemon=True)
    thread.start()

    return JSONResponse({"job_id": job_id})

@router.get("/ai-job/{job_id}")
async def get_ai_job_status(job_id: str):
    job = AI_JOBS.get(job_id)
    if not job:
        return JSONResponse({"message": "job not found"}, status_code=404)
    # Return a shallow copy to avoid accidental mutation
    return JSONResponse({
        "status": job.get("status"),
        "progress": job.get("progress", 0),
        "result_count": job.get("result_count", 0),
        "prefill": job.get("prefill", {}),
        "error": job.get("error"),
        "matched_ids": job.get("matched_ids", []),
    })

# -------------------------
# Candidate detail (dynamic) - MUST BE LAST to avoid path clashes
# -------------------------
@router.get("/{candidate_id}")
async def get_candidate(candidate_id: int, db: Session = Depends(get_db)):
    cand = db.query(Candidate).filter(Candidate.candidates_id == candidate_id).first()
    if not cand:
        return JSONResponse({}, status_code=404)
    # try to find mapping for this candidate (if any)
    try:
        mapping = db.query(CandidateJDMapping).filter(CandidateJDMapping.candidate_id == candidate_id).order_by(getattr(CandidateJDMapping, "created_at", CandidateJDMapping.jd_id).desc()).first()
    except Exception:
        mapping = None

    payload = {
        "candidates_id": cand.candidates_id,
        "candidate_name": cand.candidate_name,
        "email": cand.email,
        "contact": cand.contact,
        "location": cand.location,
        "skillset": cand.skillset,
        "it_experience": getattr(cand, "it_experience", None),
        "relevant_experience": getattr(cand, "relevant_experience", None),
        "education": getattr(cand, "education", None),
        "company": getattr(cand, "company", None),
        "resumelinks": getattr(cand, "resumelinks", None),
        "clients": getattr(cand, "clients", None),
        "notice_period": getattr(cand, "notice_period", None),
        "recruitment_notes": getattr(cand, "recruitment_notes", "") or "",
        "comment": getattr(cand, "comment", "") or "",
        "ai_score": getattr(cand, "ai_score", None),
        "ai_explanation": getattr(cand, "ai_explanation", "") or "",
        "mapping_jd_id": getattr(mapping, "jd_id", None) if mapping else None,
    }
    return JSONResponse(payload)

# -------------------------
# End of file
# -------------------------


# -------------------------
# Dropdown AI search (uses selected Job's JD link to run AI matching)
@router.post("/dropdown-ai-search")
async def dropdown_ai_search(request: Request, job_id: str = Form(...), db: Session = Depends(get_db)):
    """
    Trigger AI matching by selecting a Job from the dropdowns.
    This reads the job record, obtains the JD link, extracts features and runs the same
    ai_match_jd_with_resumes batching logic used by advanced_search. Returns the search page.

    NOTE: Modified to include already-linked candidates (previously they were excluded).
    """
    # Resolve job record robustly (support multiple id column names)
    job = None
    try:
        filters = []
        if hasattr(Job, "job_id"):
            try:
                filters.append(getattr(Job, "job_id") == job_id)
            except Exception:
                pass
        if hasattr(Job, "id"):
            try:
                # attempt numeric match if job_id looks like int
                try:
                    jid_int = int(job_id)
                except Exception:
                    jid_int = None
                if jid_int is not None:
                    filters.append(getattr(Job, "id") == jid_int)
                else:
                    filters.append(getattr(Job, "id") == job_id)
            except Exception:
                pass
        if filters:
            job = db.query(Job).filter(or_(*filters)).first()
        else:
            # fallback - attempt simple filter by job_id attribute if present
            try:
                job = db.query(Job).filter(getattr(Job, "job_id") == job_id).first()
            except Exception:
                job = None
    except Exception:
        job = None

    if not job:
        return templates.TemplateResponse("search.html", {
            "request": request,
            "results": [],
            "skills": "",
            "location": "",
            "experience": "",
            "clients": _get_active_clients(db),
            "error": "Invalid job selected.",
        })

    # find a JD link on the job object using common attribute names
    jd_link = _first_attr(job, ["jd_link", "jd_drive_link", "job_link", "job_drive_link", "drive_link", "jd_url", "description_link"]) or ""
    if not jd_link:
        # some systems store JD text in a 'description' field - use that as fallback
        jd_link = _first_attr(job, ["description", "job_description", "jd_text"]) or ""

    # fetch JD text (helper handles docs/drive/pdf/docx/html)
    try:
        jd_text = fetch_text_from_url(jd_link) if callable(fetch_text_from_url) else (jd_link or "")
        if not jd_text and jd_link and isinstance(jd_link, str):
            # If fetch failed but jd_link looks like actual plain text, use it
            jd_text = jd_link
    except Exception:
        jd_text = jd_link or ""

    # extract prefill features
    try:
        extracted = extract_jd_features(jd_text) or {}
    except Exception:
        extracted = {}
    pre_skills = extracted.get("skills", "") or ""
    pre_location = extracted.get("location", "") or ""
    pre_experience = extracted.get("experience", "") or ""

    # Prefilter candidates (same approach as advanced_search)
    q = db.query(Candidate)
    if pre_skills:
        tokens = [t.strip() for t in pre_skills.split(",") if t.strip()]
        if tokens:
            filters = [func.lower(func.coalesce(Candidate.skillset, "")).like(f"%{t.lower()}%") for t in tokens]
            q = q.filter(or_(*filters))
    if pre_location:
        try:
            q = q.filter(func.lower(func.coalesce(Candidate.location, "")).like(f"%{pre_location.strip().lower()}%"))
        except Exception:
            pass

    all_candidates = q.order_by(getattr(Candidate, "candidates_id", Candidate)).all()

    # enforce strict token-level location & experience
    if pre_location:
        all_candidates = [c for c in all_candidates if _location_matches(getattr(c, "location", "") or "", pre_location)]

    min_m = max_m = None
    if pre_experience and str(pre_experience).strip():
        try:
            min_m, max_m = parse_experience_filter_input(pre_experience)
        except Exception:
            min_m, max_m = None, None
        if min_m is not None:
            all_candidates = _filter_candidates_by_experience(all_candidates, min_m, max_m)

    # Batch AI scoring (10 at a time, preserve existing behavior)
    batch = 10
    matched_ids = set()
    score_map = {}
    expl_map = {}

    for i in range(0, len(all_candidates), batch):
        slice_batch = all_candidates[i:i+batch]
        try:
            scored = ai_match_jd_with_resumes(jd_text, slice_batch)
        except Exception:
            scored = []
        for item in (scored or []):
            cid = item.get("candidate_id") or item.get("candidates_id") or item.get("id")
            score = item.get("ai_score") or item.get("score") or 0
            expl = item.get("explanation") or item.get("reasons") or item.get("ai_explanation") or ""
            if cid:
                try:
                    cid = int(cid)
                    matched_ids.add(cid)
                    score_map[cid] = int(score)
                    if expl:
                        expl_map[cid] = expl
                except Exception:
                    continue

    results = []
    if matched_ids:
        # NOTE: changed here — do NOT exclude already-mapped candidates.
        # Instead we will include mapped candidates and attach mapping metadata so UI can display them.

        # Fetch the candidate rows for matched ids
        found_q = db.query(Candidate).filter(Candidate.candidates_id.in_(list(matched_ids)))
        found = found_q.all()

        # Build mapping rows for the found candidates so we can attach mapping metadata (is_linked, existing_jd_ids, mapping_display)
        from collections import defaultdict
        cand_ids = [getattr(c, "candidates_id", None) for c in found if getattr(c, "candidates_id", None) is not None]
        mappings_by_cid = defaultdict(list)
        if cand_ids:
            try:
                map_rows = db.query(CandidateJDMapping).filter(CandidateJDMapping.candidate_id.in_(cand_ids)).all()
                for r in map_rows:
                    cid_key = getattr(r, "candidate_id", None)
                    if cid_key is not None:
                        mappings_by_cid[cid_key].append(r)
            except Exception:
                mappings_by_cid = defaultdict(list)

        # Build job/manager/client lookup maps (best-effort) similar to manual search logic so mapping_display is useful
        mapping_info_map = {}
        try:
            all_job_ids = set()
            for lst in mappings_by_cid.values():
                for m in lst:
                    jid = getattr(m, "jd_id", None)
                    if jid is not None:
                        try:
                            all_job_ids.add(int(jid))
                        except Exception:
                            all_job_ids.add(jid)

            job_map = {}
            if all_job_ids:
                id_col = _first_column(Job, ["job_id", "id", "jobId"])
                if id_col is not None:
                    try:
                        jobs = db.query(Job).filter(id_col.in_(list(all_job_ids))).all()
                    except Exception:
                        jobs = []
                    for j in jobs:
                        try:
                            job_id_val = _first_attr(j, ["job_id", "id", "jobId"])
                            job_key = int(job_id_val) if isinstance(job_id_val, (int, str)) and str(job_id_val).isdigit() else job_id_val
                            job_map[job_key] = j
                        except Exception:
                            continue

            # collect manager (vendor) ids from jobs
            manager_ids = set()
            for j in job_map.values():
                mid = _first_attr(j, ["manager_id", "managerId", "manager", "vendor_id"])
                if mid is not None:
                    try:
                        manager_ids.add(int(mid))
                    except Exception:
                        manager_ids.add(mid)

            manager_map = {}
            if manager_ids:
                mgr_col = _first_column(Manager, ["manager_id", "id", "vendor_id", "managerId"])
                if mgr_col is not None:
                    try:
                        managers = db.query(Manager).filter(mgr_col.in_(list(manager_ids))).all()
                    except Exception:
                        managers = []
                    for m in managers:
                        try:
                            mid_val = _first_attr(m, ["manager_id", "id", "vendor_id", "managerId"])
                            key = int(mid_val) if isinstance(mid_val, (int, str)) and str(mid_val).isdigit() else mid_val
                            manager_map[key] = m
                        except Exception:
                            continue

            # collect client ids from managers
            client_ids = set()
            for m in manager_map.values():
                cid = _first_attr(m, ["client_id", "clientId", "client"])
                if cid is not None:
                    try:
                        client_ids.add(int(cid))
                    except Exception:
                        client_ids.add(cid)

            client_map = {}
            if client_ids:
                ccol = _first_column(Client, ["client_id", "id", "clientId"])
                if ccol is not None:
                    try:
                        clients = db.query(Client).filter(ccol.in_(list(client_ids))).all()
                    except Exception:
                        clients = []
                    for cobj in clients:
                        try:
                            cid_val = _first_attr(cobj, ["client_id", "id", "clientId"])
                            key = int(cid_val) if isinstance(cid_val, (int, str)) and str(cid_val).isdigit() else cid_val
                            client_map[key] = cobj
                        except Exception:
                            continue

            # now build mapping_info_map per candidate id
            for cid_key, lst in mappings_by_cid.items():
                info_list = []
                for m in lst:
                    jid = getattr(m, "jd_id", None)
                    job = None
                    job_title = ""
                    vendor_name = ""
                    client_name = ""
                    try:
                        jkey = int(jid) if isinstance(jid, (int, str)) and str(jid).isdigit() else jid
                        job = job_map.get(jkey)
                    except Exception:
                        job = None
                    if job:
                        job_title = _first_attr(job, ["job_title", "title", "jobTitle"]) or ""
                        mid = _first_attr(job, ["manager_id", "managerId", "manager", "vendor_id"])
                        try:
                            mkey = int(mid) if isinstance(mid, (int, str)) and str(mid).isdigit() else mid
                        except Exception:
                            mkey = mid
                        manager = manager_map.get(mkey)
                        if manager:
                            vendor_name = _first_attr(manager, ["manager_name", "name", "vendor_name", "managerName"]) or ""
                            client_id_ref = _first_attr(manager, ["client_id", "clientId", "client"])
                            try:
                                ck = int(client_id_ref) if isinstance(client_id_ref, (int, str)) and str(client_id_ref).isdigit() else client_id_ref
                            except Exception:
                                ck = client_id_ref
                            client_obj = client_map.get(ck)
                            if client_obj:
                                client_name = _first_attr(client_obj, ["client_name", "name", "clientName"]) or ""
                    info_list.append({
                        "jd_id": jid,
                        "job_title": job_title or "",
                        "vendor_name": vendor_name or "",
                        "client_name": client_name or "",
                        "mapping_id": getattr(m, "id", None) or getattr(m, "mapping_id", None)
                    })
                mapping_info_map[cid_key] = info_list

        except Exception:
            mapping_info_map = {}

        # produce result rows with mapping metadata attached
        for c in found:
            cid = getattr(c, "candidates_id", None)
            # attach AI score & explanation (best-effort)
            if cid in score_map:
                try:
                    setattr(c, "ai_score", score_map[cid])
                except Exception:
                    pass
            if cid in expl_map:
                try:
                    setattr(c, "ai_explanation", expl_map[cid])
                except Exception:
                    pass

            mapping_list = mappings_by_cid.get(cid, [])
            base_map = mapping_list[0] if mapping_list else None
            row = _candidate_to_row(c, base_map)

            info = mapping_info_map.get(cid, [])
            row["is_linked"] = bool(info)
            row["existing_jd_ids"] = [i.get("jd_id") for i in info]

            try:
                row["mapping_display"] = " | ".join([ (f"{(i.get('client_name') or '').strip() + (' > ' if (i.get('client_name') or '') else '')}{(i.get('vendor_name') or '')}{(' > ' if (i.get('vendor_name') or '') else '')}{(i.get('job_title') or '')}").strip(" > ") for i in info ]) or ""
            except Exception:
                row["mapping_display"] = ""

            results.append(row)

        # --- sort AI-matched results by ai_score (descending) ---
        try:
            results.sort(key=lambda r: int(r.get('ai_score') or r.get('score') or 0), reverse=True)
        except Exception:
            pass

        try:
            db.commit()
        except Exception:
            db.rollback()

    clients = _get_active_clients(db)
    return templates.TemplateResponse("search.html", {
        "request": request,
        "results": results,
        "skills": pre_skills,
        "location": pre_location,
        "experience": pre_experience,
        "prefill_skills": pre_skills,
        "prefill_location": pre_location,
        "prefill_experience": pre_experience,
        "clients": clients,
    })
