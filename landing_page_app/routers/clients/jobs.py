from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from landing_page_app.database import get_db
from landing_page_app.models.jobs import Job
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.clients import Client
from landing_page_app.models.candidate_status_history import CandidateJDMapping

router = APIRouter()
templates = Jinja2Templates(directory="landing_page_app/templates")


# ------------------------------
# Jobs Overview → Count of jobs by title
# ------------------------------
@router.get("/jobs/overview")
def jobs_overview(db: Session = Depends(get_db)):
    job_counts = db.query(Job.job_title, func.count(Job.job_id)) \
                   .group_by(Job.job_title).all()
    return {title or "Unknown": count for title, count in job_counts}


# ------------------------------
# View All Jobs for a Client
# ------------------------------
@router.get("/clients/{client_id}")
def client_jobs_page(request: Request, client_id: int, db: Session = Depends(get_db), message: str = ""):
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    jobs = db.query(Job).filter(Job.client_id == client_id).order_by(Job.created_at.desc()).all()
    for job in jobs:
        if not hasattr(job, 'status') or job.status is None:
            job.status = 'inactive'

    return templates.TemplateResponse(
        "client_jobs.html",
        {"request": request, "jobs": jobs, "client": client, "message": message}
    )


# ------------------------------
# Add a New Job under a Client
# ------------------------------
@router.post("/{client_id}/add-job")
def add_job(
    request: Request,
    client_id: int,
    job_title: str = Form(...),
    jd_link: str = Form(""),
    db: Session = Depends(get_db)
):
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    message = ""
    job_title = job_title.strip()

    if not job_title:
        message = "Job title is required!"
    else:
        existing_job = db.query(Job).filter(Job.client_id == client_id, Job.job_title == job_title).first()
        if existing_job:
            message = f"Job '{job_title}' already exists for this client!"
        else:
            new_job = Job(
                client_id=client_id,
                job_title=job_title,
                job_description=jd_link,
                created_at=datetime.utcnow(),
                status="inactive"
            )
            db.add(new_job)
            db.commit()
            db.refresh(new_job)
            message = f"Job '{job_title}' added successfully!"

    jobs = db.query(Job).filter(Job.client_id == client_id).order_by(Job.created_at.desc()).all()
    return templates.TemplateResponse(
        "client_jobs.html",
        {"request": request, "jobs": jobs, "client": client, "message": message}
    )


# ------------------------------
# Toggle Job Status
# ------------------------------
@router.post("/{client_id}/toggle-job/{job_id}")
def toggle_job_status(client_id: int, job_id: int, request: Request, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.client_id == client_id, Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = "inactive" if job.status == "active" else "active"
    db.commit()

    jobs = db.query(Job).filter(Job.client_id == client_id).order_by(Job.created_at.desc()).all()
    client = db.query(Client).filter(Client.client_id == client_id).first()

    return templates.TemplateResponse(
        "client_jobs.html",
        {"request": request, "jobs": jobs, "client": client, "message": "Job status updated successfully!"}
    )


# ------------------------------
# Delete Job
# ------------------------------
@router.post("/{client_id}/delete-job/{job_id}")
def delete_job(client_id: int, job_id: int, request: Request, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.client_id == client_id, Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    db.delete(job)
    db.commit()

    jobs = db.query(Job).filter(Job.client_id == client_id).order_by(Job.created_at.desc()).all()
    client = db.query(Client).filter(Client.client_id == client_id).first()

    return templates.TemplateResponse(
        "client_jobs.html",
        {"request": request, "jobs": jobs, "client": client, "message": "Job deleted successfully!"}
    )


# ------------------------------
# View Candidates Linked to a Job
# ------------------------------
@router.get("/job/{job_id}/candidates")
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
