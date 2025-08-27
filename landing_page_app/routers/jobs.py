from fastapi import APIRouter, Depends, Request, Form
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from landing_page_app.database import get_db
from landing_page_app.models.jobs import Job
from landing_page_app.models.user import User
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.routers.auth import get_current_user  # ✅ import auth dependency

router = APIRouter(prefix="/jobs", tags=["Jobs"])
templates = Jinja2Templates(directory="landing_page_app/templates")

# -----------------------
# Jobs Overview
# -----------------------
@router.get("/overview")
def jobs_overview(db: Session = Depends(get_db)):
    job_counts = db.query(Job.job_title, func.count(Job.job_id)).group_by(Job.job_title).all()
    return {title or "Unknown": count for title, count in job_counts}


# -----------------------
# View Candidates for a Job
# -----------------------
@router.get("/{job_id}/candidates")
def job_candidates(job_id: int, db: Session = Depends(get_db)):
    candidates = (
        db.query(Candidate)
        .join(CandidateJDMapping, Candidate.candidates_id == CandidateJDMapping.candidate_id)
        .filter(CandidateJDMapping.jd_id == job_id)
        .all()
    )
    results = []
    for c in candidates:
        latest_status = (
            db.query(CandidateJDMapping.stage)
            .filter(CandidateJDMapping.candidate_id == c.candidates_id)
            .order_by(CandidateJDMapping.updated_at.desc())
            .first()
        )
        results.append({
            "candidates_id": c.candidates_id,
            "candidate_name": c.candidate_name,
            "status": latest_status[0] if latest_status else "Not Updated"
        })
    return results


# -----------------------
# View All Jobs for a Client
# -----------------------
@router.get("/client/{client_id}")
def client_jobs_page(request: Request, client_id: int, db: Session = Depends(get_db), message: str = ""):
    jobs = (
        db.query(Job)
        .filter(Job.client_id == client_id)
        .order_by(Job.created_at.desc())
        .all()
    )

    # ✅ Fetch creator and updater names
    job_list = []
    for job in jobs:
        created_by_name = db.query(User.full_name).filter(User.id == job.created_by).scalar() if job.created_by else "N/A"
        updated_by_name = db.query(User.full_name).filter(User.id == job.updated_by).scalar() if job.updated_by else "N/A"

        job_list.append({
            "job_id": job.job_id,
            "job_title": job.job_title,
            "job_description": job.job_description,
            "status": job.status,
            "created_by": created_by_name,
            "created_at": job.created_at,
            "updated_by": updated_by_name,
            "updated_at": job.updated_at
        })

    return templates.TemplateResponse(
        "client_jobs.html",
        {"request": request, "jobs": job_list, "client_id": client_id, "message": message}
    )


# -----------------------
# Add a New Job under a Client
# -----------------------
@router.post("/client/{client_id}")
def add_job(
    request: Request,
    client_id: int,
    job_title: str = Form(...),
    job_description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # ✅ Get logged-in user
):
    message = ""
    job_title = job_title.strip()

    if not job_title:
        message = "Job title is required!"
    else:
        # Check if job already exists for this client
        existing_job = db.query(Job).filter(Job.client_id == client_id, Job.job_title == job_title).first()
        if existing_job:
            message = f"Job '{job_title}' already exists for this client!"
        else:
            new_job = Job(
                client_id=client_id,
                job_title=job_title,
                job_description=job_description,
                created_at=datetime.utcnow(),
                created_by=current_user.id  # ✅ Save created_by
            )
            db.add(new_job)
            db.commit()
            db.refresh(new_job)
            message = f"Job '{job_title}' added successfully!"

    jobs = db.query(Job).filter(Job.client_id == client_id).order_by(Job.created_at.desc()).all()
    return templates.TemplateResponse(
        "client_jobs.html",
        {"request": request, "jobs": jobs, "client_id": client_id, "message": message}
    )
