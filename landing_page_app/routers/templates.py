# landing_page_app/routers/templates.py
from fastapi import APIRouter, Request, Query, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, Integer, cast
import re

from landing_page_app.database import SessionLocal
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.clients import Client

# NEW: import user + auth helper
from landing_page_app.models.user import User, UserRole
from landing_page_app.deps import get_current_user

router = APIRouter(tags=["Templates"])
templates = Jinja2Templates(directory="landing_page_app/templates")


# ---------- helper: check admin ----------
def _is_admin(user: User | None) -> bool:
    if not user:
        return False
    role = getattr(user, "role", None)
    try:
        return role == UserRole.ADMIN
    except Exception:
        # handle stringy roles like "ADMIN"
        return str(role).upper() == "ADMIN"


@router.get("/", response_class=HTMLResponse)
async def root(
    request: Request,
    user: User = Depends(get_current_user),   # NEW: current user
):
    hiring_pipeline = [
        {"stage": "Screening", "count": 0},
        {"stage": "Submissions", "count": 0},
        {"stage": "Interview", "count": 1},
        {"stage": "Offered", "count": 0},
        {"stage": "Hired", "count": 1},
        {"stage": "Rejected", "count": 0},
        {"stage": "Archived", "count": 0}
    ]

    time_to_fill = [
        {"job_opening": "All Jobs (Avg.)", "candidates_per_position": 1, "since_creation": 15, "since_approval": 0, "delay_days": 0, "status": "On track"},
        {"job_opening": "Product Analyst", "candidates_per_position": 1, "since_creation": 15, "since_approval": None, "delay_days": 0, "status": "On track"}
    ]

    time_to_hire = [
        {"candidate": "All Candidates (Avg.)", "job_opening": "-", "days": 15},
        {"candidate": "Christina Palaskas", "job_opening": "Product Analyst", "days": 15}
    ]

    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "hiring_pipeline": hiring_pipeline,
            "time_to_fill": time_to_fill,
            "time_to_hire": time_to_hire,
            # NEW: used by base.html to hide/show "Go to Admin"
            "is_admin": _is_admin(user),
            "user": user,
        },
    )


# -------------------- SEARCH PAGE --------------------
@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    skills: str = Query(None),
    location: str = Query(None),
    experience: str = Query(None),
    user: User = Depends(get_current_user),  # NEW
):
    if not skills and not location and not experience:
        return templates.TemplateResponse(
            "search.html",
            {
                "request": request,
                "skills": skills,
                "location": location,
                "experience": experience,
                "results": [],
                "is_admin": _is_admin(user),  # NEW
                "user": user,
            },
        )

    with SessionLocal() as db:
        query = db.query(Candidate)

        if skills:
            for skill in [s.strip().lower() for s in skills.split(",")]:
                query = query.filter(func.lower(Candidate.skillset).like(f"%{skill}%"))

        if location:
            query = query.filter(func.lower(Candidate.location).like(f"%{location.lower()}%"))

        if experience:
            clean_exp = re.sub(r"[^0-9\-]", "", experience)
            try:
                if "-" in clean_exp:
                    min_exp, max_exp = map(int, clean_exp.split("-"))
                    query = query.filter(
                        cast(func.nullif(func.regexp_replace(Candidate.it_experience, r'(\d+)\D*.*', r'\1', 'g'), ''), Integer) >= min_exp,
                        cast(func.nullif(func.regexp_replace(Candidate.it_experience, r'(\d+)\D*.*', r'\1', 'g'), ''), Integer) <= max_exp
                    )
                else:
                    min_exp = int(clean_exp)
                    query = query.filter(
                        cast(func.nullif(func.regexp_replace(Candidate.it_experience, r'(\d+)\D*.*', r'\1', 'g'), ''), Integer) >= min_exp
                    )
            except ValueError:
                pass

        candidates_data = query.all()

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "skills": skills,
            "location": location,
            "experience": experience,
            "results": [
                {
                    "candidates_id": c.candidates_id,
                    "candidate_name": c.candidate_name,
                    "contact": c.contact,
                    "email": c.email,
                    "location": c.location,
                    "skillset": c.skillset,
                    "relevant_experience": c.relevant_experience,
                    "it_experience": c.it_experience,
                    "education": c.education,
                    "company": c.company,
                    "resumelinks": c.resumelinks,
                    "comment": c.comment,
                    "clients": c.clients,
                    "notice_period": c.notice_period,
                } for c in candidates_data
            ],
            "is_admin": _is_admin(user),  # NEW
            "user": user,
        },
    )


@router.get("/new-arrivals", response_class=HTMLResponse)
async def new_arrivals_page(
    request: Request,
    user: User = Depends(get_current_user),  # NEW
):
    with SessionLocal() as db:
        clients_data = db.query(Client).order_by(Client.created_at.desc()).limit(10).all()

    return templates.TemplateResponse(
        "new_arrivals.html",
        {
            "request": request,
            "clients": clients_data,
            "is_admin": _is_admin(user),  # NEW
            "user": user,
        },
    )
