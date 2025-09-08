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
    update_job,
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
def toggle_job_status_route(request: Request, manager_id: int, job_id: int, db: Session = Depends(get_db)):
    job = toggle_job_status(db, job_id, manager_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    message = f"Job '{job.job_title}' status updated!"

    # If the client requested JSON (AJAX), return JSON for better UX; otherwise keep redirect behaviour
    content_type = request.headers.get("content-type", "").lower()
    accept = request.headers.get("accept", "").lower()
    xreq = request.headers.get("x-requested-with", "").lower()

    if "application/json" in content_type or "application/json" in accept or xreq == "xmlhttprequest":
        # return JSON data that client-side can use to update the UI
        return {
            "job_id": job.job_id,
            "job_title": job.job_title,
            "status": job.status,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "updated_by": job.updated_by
        }
    else:
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


# -----------------------------
# 7. Edit / Update Job (supports JSON/AJAX and regular form submit)
# -----------------------------
@router.post("/{manager_id}/edit-job/{job_id}", name="edit_job")
async def edit_job(request: Request, manager_id: int, job_id: int, db: Session = Depends(get_db)):
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")

    # Find the job
    job = db.query(Job).filter(Job.job_id == job_id, Job.manager_id == manager_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    content_type = request.headers.get("content-type", "").lower()

    # Support JSON body (AJAX) or form submit
    if "application/json" in content_type:
        body = await request.json()
        new_title = (body.get("job_title") or "").strip()
        new_description = (body.get("job_description") or "").strip()
        updated_by = body.get("updated_by")
    else:
        form = await request.form()
        new_title = (form.get("job_title") or "").strip()
        new_description = (form.get("job_description") or "").strip()
        updated_by = form.get("updated_by")

    if not new_title:
        message = "Job title is required!"
        if "application/json" in content_type:
            raise HTTPException(status_code=400, detail=message)
        else:
            redirect_url = str(request.url_for("manager_jobs_page", manager_id=manager_id)) + f"?message={message}"
            return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    updated_job = update_job(db, manager_id, job_id, new_title, new_description, updated_by)

    if not updated_job:
        raise HTTPException(status_code=404, detail="Job update failed")

    message = f"Job '{new_title}' updated successfully!"

    if "application/json" in content_type:
        return {
            "job_id": updated_job.job_id,
            "job_title": updated_job.job_title,
            "job_description": updated_job.job_description,
            "updated_at": updated_job.updated_at.isoformat() if updated_job.updated_at else None,
            "updated_by": updated_job.updated_by,
            "status": updated_job.status,
            "message": message
        }
    else:
        redirect_url = str(request.url_for("manager_jobs_page", manager_id=manager_id)) + f"?message={message}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
