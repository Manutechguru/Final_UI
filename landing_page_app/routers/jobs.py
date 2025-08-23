from fastapi import APIRouter, Depends, Request, Form
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from landing_page_app.database import get_db
from landing_page_app.models.jobs import Job
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping

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
    jobs = db.query(Job).filter(Job.client_id == client_id).order_by(Job.created_at.desc()).all()
    return templates.TemplateResponse(
        "client_jobs.html",
        {"request": request, "jobs": jobs, "client_id": client_id, "message": message}
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
    db: Session = Depends(get_db)
):
    message = ""
    job_title = job_title.strip()

    if not job_title:
        message = "Job title is required!"
    else:
        # Optional: check if the same job exists for this client
        existing_job = db.query(Job).filter(Job.client_id == client_id, Job.job_title == job_title).first()
        if existing_job:
            message = f"Job '{job_title}' already exists for this client!"
        else:
            new_job = Job(
                client_id=client_id,
                job_title=job_title,
                job_description=job_description,
                created_at=datetime.utcnow()
            )
            db.add(new_job)
            db.commit()
            db.refresh(new_job)
            message = f"Job '{job_title}' added successfully!"

    # Return updated jobs list for the client
    jobs = db.query(Job).filter(Job.client_id == client_id).order_by(Job.created_at.desc()).all()
    return templates.TemplateResponse(
        "client_jobs.html",
        {"request": request, "jobs": jobs, "client_id": client_id, "message": message}
    )
