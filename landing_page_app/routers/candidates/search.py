# landing_page_app/routers/candidates/search.py

from fastapi import APIRouter, Request, Query, Depends, HTTPException, Form
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List

from landing_page_app.database import get_db
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.models.clients import Client

from landing_page_app.routers.utils.candidates_utils import (
    parse_text_experience_to_months,
    parse_experience_filter_input
)
from landing_page_app.routers.utils.jd_utils import (
    fetch_jd_text,
    extract_jd_keywords
)

templates = Jinja2Templates(directory="landing_page_app/templates")
router = APIRouter(prefix="/candidates", tags=["Candidates Search"])

# ----------------------------------------------------------------------
# BASIC SEARCH
# ----------------------------------------------------------------------
@router.api_route("/search", methods=["GET", "POST"])
async def search_candidates(
    request: Request,
    skills: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    experience: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Candidate search with filters:
    - Skills (comma-separated)
    - Location
    - Experience range
    Excludes candidates already linked to any JD.
    """
    # If form is submitted via POST, override query params
    if request.method.upper() == "POST":
        form = await request.form()
        skills = form.get("skills", skills)
        location = form.get("location", location)
        experience = form.get("experience", experience)

    query = db.query(Candidate)

    # Exclude candidates already mapped to any JD
    subq = db.query(CandidateJDMapping.candidate_id).distinct().subquery()
    query = query.filter(~Candidate.candidates_id.in_(subq))

    # Filter by skills
    if skills:
        skill_tokens = [t.strip().lower() for t in skills.split(",") if t.strip()]
        for tok in skill_tokens:
            query = query.filter(func.lower(func.coalesce(Candidate.skillset, "")).like(f"%{tok}%"))

    # Filter by location
    if location:
        loc = location.strip().lower()
        query = query.filter(func.lower(func.coalesce(Candidate.location, "")) .like(f"%{loc}%"))

    rows = query.order_by(Candidate.candidates_id).all()

    # Handle experience range
    exp_min = exp_max = None
    if experience:
        try:
            exp_min, exp_max = parse_experience_filter_input(experience)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid experience value. Use 'X years', 'X-Y', or 'X years Y months'."
            )

    results = []
    for c in rows:
        # Filter by experience
        if experience:
            mths = parse_text_experience_to_months(c.it_experience)
            if mths is None:
                continue
            if exp_min is not None and mths < exp_min:
                continue
            if exp_max is not None and mths > exp_max:
                continue

        # Get latest stage
        latest_status = (
            db.query(CandidateJDMapping.stage)
            .filter(CandidateJDMapping.candidate_id == c.candidates_id)
            .order_by(CandidateJDMapping.updated_at.desc())
            .first()
        )
        status_val = latest_status[0] if latest_status else "Not Updated"

        results.append({
            "candidates_id": c.candidates_id,
            "candidate_name": c.candidate_name,
            "email": c.email,
            "contact": c.contact,
            "location": c.location,
            "skillset": c.skillset or "",
            "it_experience": c.it_experience,
            "notice_period": c.notice_period,
            "status": status_val,
            "resumelinks": getattr(c, "resumelinks", None),
        })

    clients = db.query(Client).order_by(Client.client_name).all()
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "results": results,
            "skills": skills or "",
            "location": location or "",
            "experience": experience or "",
            "clients": clients,
            "advanced_from_jd": False,
        }
    )


# ----------------------------------------------------------------------
# ADVANCED SEARCH → Extract from JD
# ----------------------------------------------------------------------
@router.post("/advanced-search")
async def advanced_search(
    request: Request,
    jd_drive_link: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Advanced search → Fetch JD from Google Drive/Docs,
    extract skills, location, and experience,
    pre-fill the search form.
    """
    jd_text = fetch_jd_text(jd_drive_link)
    extracted = extract_jd_keywords(jd_text)
    clients = db.query(Client).order_by(Client.client_name).all()

    # Convert lists to comma-separated strings for form fields
    skills_str = ", ".join(extracted.get("skills", []))
    location_str = ", ".join(extracted.get("locations", []))
    experience_str = ""  # Optional: parse experience from JD if needed

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "results": [],
            "skills": skills_str,
            "location": location_str,
            "experience": experience_str,
            "clients": clients,
            "advanced_from_jd": True,
            "jd_drive_link": jd_drive_link,
        }
    )
