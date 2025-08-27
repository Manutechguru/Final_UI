from fastapi import APIRouter, Request, Form, HTTPException, Depends, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from landing_page_app.database import get_db
from landing_page_app.routers.utils.jobs_utils import (
    get_manager_by_id,
    get_jobs_by_manager,
    add_new_job,
    toggle_job_status,
    delete_job,
)
from landing_page_app.models.jobs import Job

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
# -----------------------------
@router.post("/{manager_id}/toggle-job/{job_id}", name="toggle_job_status")
def toggle_job_status_route(manager_id: int, job_id: int, db: Session = Depends(get_db)):
    job = toggle_job_status(db, job_id, manager_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
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

    # ✅ Redirect to the working JD candidates page
    return RedirectResponse(url=f"/candidates/jd-candidates/{job.job_id}")
