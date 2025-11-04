# landing_page_app/routers/clients/alljobs.py
from fastapi import APIRouter, Request, Query, HTTPException, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import joinedload
from sqlalchemy import desc
from landing_page_app.database import SessionLocal
from landing_page_app.models.jobs import Job
from landing_page_app.models.clients import Client
from landing_page_app.models.managers import Manager
from fastapi.templating import Jinja2Templates
from typing import Optional

# ✅ Added imports for user injection
from landing_page_app.models.user import User
from landing_page_app.routers.auth import get_current_user

router = APIRouter(prefix="/clients/all_jobs", tags=["All Jobs"])
templates = Jinja2Templates(directory="landing_page_app/templates")


@router.get("")
@router.get("/")
def all_jobs_page(
    request: Request,
    user: User = Depends(get_current_user),  # ✅ Added dependency
):
    """Render the All Jobs HTML page."""
    with SessionLocal() as db:
        clients = db.query(Client).order_by(Client.client_name).all()
        managers = db.query(Manager).order_by(Manager.manager_name).all()

    return templates.TemplateResponse(
        "all_jobs.html",
        {
            "request": request,
            "clients": clients,
            "managers": managers,
            "user": user,  # ✅ Added user context
        },
    )


@router.get("/data")
def get_all_jobs_data(
    client_id: Optional[int] = Query(None),
    manager_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="Filter by job status: Active or Inactive"),
    recent: Optional[bool] = Query(False, description="Sort by most recently created")
):
    """Fetch job data with optional filters:
    - client_id
    - manager_id
    - status (Active / Inactive)
    - recent (True = sort by latest created first)
    """
    with SessionLocal() as db:
        query = db.query(Job).options(
            joinedload(Job.manager).joinedload(Manager.client)
        )

        # Apply filters
        if client_id is not None:
            query = query.join(Job.manager).filter(Manager.client_id == client_id)
        if manager_id is not None:
            query = query.filter(Job.manager_id == manager_id)
        if status:
            query = query.filter(Job.status.ilike(status))  # case-insensitive

        # Apply sorting
        if recent:
            query = query.order_by(desc(Job.created_at))
        else:
            query = query.order_by(Job.created_at)

        jobs = query.all()

        result = []
        for job in jobs:
            manager_id_val = job.manager.manager_id if job.manager else None
            client_id_val = job.manager.client.client_id if job.manager and job.manager.client else None

            result.append({
                "job_id": job.job_id,
                "job_title": job.job_title,
                "job_description": job.job_description or "-",
                "manager_id": manager_id_val,  # 👈 added
                "client_id": client_id_val,    # 👈 optional but useful
                "manager_name": job.manager.manager_name if job.manager else "-",
                "client_name": job.manager.client.client_name if job.manager and job.manager.client else "-",
                "status": job.status,
                "created_at": job.created_at.strftime("%Y-%m-%d"),
                "link": f"/candidates/jd-candidates/{job.job_id}" if job.job_id else "#",
                "job_page_link": f"/managers/jobs/{manager_id_val}" if manager_id_val else None  # 👈 added
            })


    return {"jobs": result}


@router.delete("/{job_id}")
def delete_job(job_id: int):
    """Delete a job by ID. Returns 200 on success or 404 if not found."""
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            return JSONResponse(status_code=404, content={"detail": "Job not found"})
        db.delete(job)
        db.commit()
    return JSONResponse(status_code=200, content={"detail": "Job deleted"})


@router.get("/edit/{job_id}")
def edit_job_page(
    request: Request,
    job_id: int,
    user: User = Depends(get_current_user),  # ✅ Added dependency
):
    """Render a basic edit page for a job. (Kept for compatibility.)"""
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        clients = db.query(Client).order_by(Client.client_name).all()
        managers = db.query(Manager).order_by(Manager.manager_name).all()

    return templates.TemplateResponse(
        "job_edit.html",
        {
            "request": request,
            "job": job,
            "clients": clients,
            "managers": managers,
            "user": user,  # ✅ Added user context
        },
    )


@router.post("/edit/{job_id}")
async def update_job(request: Request, job_id: int):
    """Handle form submission from the edit modal and update the Job record."""
    form = await request.form()
    title = form.get("job_title")
    description = form.get("job_description")
    manager_id = form.get("manager_id")
    status = form.get("status")

    with SessionLocal() as db:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if title is not None:
            job.job_title = title.strip()
        if description is not None:
            job.job_description = description.strip()
        if manager_id:
            try:
                job.manager_id = int(manager_id)
            except ValueError:
                pass
        if status is not None:
            job.status = status

        db.add(job)
        db.commit()

    # Redirect back to All Jobs page after update
    return RedirectResponse(url="/clients/all_jobs", status_code=303)
