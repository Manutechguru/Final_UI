from fastapi import APIRouter, Request, Form, HTTPException, Depends, status
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import Optional

# project imports
from landing_page_app.database import get_db
from landing_page_app.models.jobs import Job
from landing_page_app.models.user import User
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.routers.auth import get_current_user

from landing_page_app.routers.utils.jobs_utils import (
    get_manager_by_id,
    get_jobs_by_manager,
    add_new_job,
    toggle_job_status,
    delete_job,
)

router = APIRouter(prefix="/managers/jobs", tags=["Jobs"])
templates = Jinja2Templates(directory="landing_page_app/templates")


# -----------------------------
# 1. Manager Jobs Page
# -----------------------------
@router.get("/{manager_id}", name="manager_jobs_page")
def manager_jobs_page(
    request: Request,
    manager_id: int,
    db: Session = Depends(get_db),
    message: str = ""
):
    """
    Show manager's jobs page.
    NOTE: Kept signature identical to your original (no auth dependency injected here)
    to avoid changing existing wiring. get_current_user is imported above so you can
    use it later if needed.
    """
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")

    jobs = get_jobs_by_manager(db, manager_id)
    return templates.TemplateResponse(
        "client_jobs.html",
        {"request": request, "manager": manager, "jobs": jobs, "message": message}
    )


# -----------------------------
# 2. Add a New Job (Manager Only)
# -----------------------------
@router.post("/{manager_id}/add-job", name="add_job")
def add_job(
    request: Request,
    manager_id: int,
    job_title: str = Form(...),
    job_description: str = Form(""),
    db: Session = Depends(get_db)
):
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")

    job_title_clean = (job_title or "").strip()
    job_description_clean = (job_description or "").strip()
    message = ""

    if not job_title_clean:
        message = "Job title is required!"
    else:
        jobs = get_jobs_by_manager(db, manager_id)
        if any(job.job_title.lower() == job_title_clean.lower() for job in jobs):
            message = f"Job '{job_title_clean}' already exists!"
        else:
            add_new_job(db, manager_id, job_title_clean, job_description_clean)
            message = f"Job '{job_title_clean}' added successfully!"

    redirect_url = str(request.url_for("manager_jobs_page", manager_id=manager_id)) + f"?message={message}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# -----------------------------
# 3. Toggle Job Status
#    - Accepts POST or PUT for compatibility with existing frontends
#    - If JSON request -> return JSON with updated fields. Otherwise -> redirect (preserve legacy)
# -----------------------------
@router.api_route("/{manager_id}/toggle-job/{job_id}", methods=["POST", "PUT"], name="toggle_job_status")
async def toggle_job_status_route(request: Request, manager_id: int, job_id: int, db: Session = Depends(get_db)):
    """
    Toggles the job status. Accepts optional JSON: {"status": "active"|"inactive", "updated_by": <id>}
    If the request has application/json content-type we respond with JSON containing the new status and updated_at.
    Otherwise we redirect back to the manager jobs page (legacy form flow).
    """
    content_type = request.headers.get("content-type", "")
    desired_status: Optional[str] = None
    updated_by: Optional[int] = None

    # Try parse JSON body if present
    try:
        if "application/json" in content_type:
            payload = await request.json()
            if isinstance(payload, dict):
                desired_status = payload.get("status")
                updated_by = payload.get("updated_by")
    except Exception:
        # ignore parse errors; fallback to toggling without explicit desired_status
        desired_status = None
        updated_by = None

    # toggle job using jobs_utils (which updates updated_at and updated_by)
    job = toggle_job_status(db, job_id, manager_id, desired_status=desired_status, updated_by=updated_by)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # If this was an AJAX/json call, return JSON with useful fields
    if "application/json" in content_type:
        return JSONResponse(
            status_code=200,
            content={
                "job_id": job.job_id,
                "status": job.status,
                "updated_at": job.updated_at.strftime("%Y-%m-%d %H:%M:%S") if job.updated_at else None,
                "updated_by": job.updated_by
            }
        )

    # Otherwise preserve previous redirect behaviour for normal form/navigation flows
    message = f"Job '{job.job_title}' status updated!"
    return RedirectResponse(
        url=f"/managers/jobs/{manager_id}?message={message}",
        status_code=status.HTTP_303_SEE_OTHER
    )


# -----------------------------
# 4. Delete Job
# -----------------------------
@router.post("/{manager_id}/delete-job/{job_id}", name="delete_job")
def delete_job_route(manager_id: int, job_id: int, db: Session = Depends(get_db)):
    success = delete_job(db, job_id, manager_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    message = "Job deleted successfully!"
    return RedirectResponse(
        url=f"/managers/jobs/{manager_id}?message={message}",
        status_code=status.HTTP_303_SEE_OTHER
    )


# -----------------------------
# 5. View Job JD
# -----------------------------
@router.get("/view-jd/{job_id}", name="view_job_jd")
def view_job_jd(request: Request, job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse(
        "view_jd.html",
        {"request": request, "job": job}
    )


# -----------------------------
# 6. Get Candidates for a Job
# -----------------------------
@router.get("/{job_id}/candidates", name="job_candidates")
def job_candidates(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return RedirectResponse(url=f"/candidates/jd-candidates/{job.job_id}")
