from fastapi import APIRouter, Request, Form, HTTPException, Depends, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from landing_page_app.database import get_db
from landing_page_app.models.clients import Client
from landing_page_app.models.jobs import Job
from landing_page_app.routers.auth import get_current_user
from landing_page_app.routers.utils.vendors_utils import (
    get_manager_by_id,
    get_managers_for_client,
    add_manager,
    delete_manager,
    toggle_manager_status,
    edit_manager,
    manager_exists,
)

# Import job utilities
from landing_page_app.routers.utils.jobs_utils import (
    get_jobs_by_manager,
    add_new_job,
    toggle_job_status_single,  # ← ADD THIS
    delete_job_single,         # ← ADD THIS  
    get_jobs_by_manager_with_status,  # ← ADD THIS
)

router = APIRouter(prefix="/vendors", tags=["Vendors"])
templates = Jinja2Templates(directory="landing_page_app/templates")
logger = logging.getLogger(__name__)

# Define IST timezone
IST = ZoneInfo("Asia/Kolkata")


def get_client_or_404(db: Session, client_id: int) -> Client:
    c = db.query(Client).filter(Client.client_id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


async def parse_desired_status(request: Request) -> Optional[str]:
    desired = None
    try:
        raw = await request.body()
    except Exception:
        raw = b""

    if raw:
        try:
            payload = await request.json()
            if isinstance(payload, dict):
                desired = payload.get("status") or payload.get("new_status") or payload.get("desired")
        except Exception:
            try:
                form = await request.form()
                desired = form.get("status") or form.get("new_status") or None
            except Exception:
                desired = None

    if desired is None:
        desired = request.query_params.get("status", None)

    if isinstance(desired, str):
        desired = desired.strip().lower()
        if desired not in ("active", "inactive"):
            raise HTTPException(status_code=400, detail="Invalid status value (must be 'active' or 'inactive')")
        return desired

    return None


# ---------- Routes ----------

@router.get("/client/{client_id}", name="list_managers")
def list_managers_page(request: Request, client_id: int, db: Session = Depends(get_db), message: str = ""):
    client = get_client_or_404(db, client_id)
    managers = get_managers_for_client(db, client_id)
    
    # Debug logging
    logger.info(f"Found {len(managers)} managers for client {client_id}")
    
    # Get jobs for each manager and handle both dict and object responses
    managers_with_jobs = []
    for manager in managers:
        # Handle both dict and object responses from get_manager_by_id
        manager_obj = manager
        if isinstance(manager, dict):
            manager_id = manager.get('manager_id')
            # Get the full manager object from database
            manager_obj = get_manager_by_id(db, manager_id)
        else:
            manager_id = manager.manager_id
            
        if manager_obj:
            jobs = get_jobs_by_manager(db, manager_id)
            logger.info(f"Manager {manager_id} has {len(jobs)} jobs")
            
            # ✅ FIXED: Extract manager name properly with multiple fallbacks
            manager_name = None
            if isinstance(manager_obj, dict):
                manager_name = manager_obj.get('manager_name')
            else:
                manager_name = getattr(manager_obj, 'manager_name', None)
            
            # If manager_name is still None, try other possible attributes
            if manager_name is None:
                if isinstance(manager_obj, dict):
                    manager_name = manager_obj.get('name') or manager_obj.get('full_name') or manager_obj.get('username')
                else:
                    manager_name = getattr(manager_obj, 'name', None) or getattr(manager_obj, 'full_name', None) or getattr(manager_obj, 'username', None)
            
            # Final fallback
            if manager_name is None:
                manager_name = f"Manager {manager_id}"
            
            # ✅ FIXED: Extract status properly
            status = None
            if isinstance(manager_obj, dict):
                status = manager_obj.get('status')
            else:
                status = getattr(manager_obj, 'status', None)
            
            # Default status if not found
            if status is None:
                status = "active"  # Default to active for new managers
            
            # Create a consistent structure for the template
            manager_data = {
                'manager_id': manager_id,
                'manager_name': manager_name,  # ✅ Now properly set
                'status': status,  # ✅ Now properly set
                'client_id': client_id,
                'jobs': jobs,
                # Include additional fields for the template if available
                'created_by': getattr(manager_obj, 'created_by', None) if not isinstance(manager_obj, dict) else manager_obj.get('created_by'),
                'created_at': getattr(manager_obj, 'created_at', None) if not isinstance(manager_obj, dict) else manager_obj.get('created_at'),
                'updated_by': getattr(manager_obj, 'updated_by', None) if not isinstance(manager_obj, dict) else manager_obj.get('updated_by'),
                'updated_at': getattr(manager_obj, 'updated_at', None) if not isinstance(manager_obj, dict) else manager_obj.get('updated_at'),
            }
            managers_with_jobs.append(manager_data)
    
    return templates.TemplateResponse(
        "managers.html",
        {
            "request": request, 
            "client": client, 
            "managers": managers_with_jobs, 
            "message": message,
            "get_jobs_by_manager": get_jobs_by_manager
        },
    )


@router.post("/client/{client_id}/add", name="add_new_manager")
def add_new_manager(
    request: Request,
    client_id: int,
    manager_name: str = Form(...),
    job_title: List[str] = Form(...),        # Multiple job titles
    job_description: List[str] = Form([]),   # Optional job descriptions
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    client = get_client_or_404(db, client_id)
    name = (manager_name or "").strip()
    message = ""

    if not name:
        message = "Manager name is required!"
        redirect_url = str(request.url_for("list_managers", client_id=client_id)) + f"?message={message}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    if manager_exists(db, client_id, name):
        message = f"Vendor '{name}' already exists!"
        redirect_url = str(request.url_for("list_managers", client_id=client_id)) + f"?message={message}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    # Clean job titles/descriptions
    clean_titles = []
    if isinstance(job_title, list):
        clean_titles = [t.strip() for t in job_title if t and t.strip()]
    elif job_title:
        clean_titles = [job_title.strip()]
    
    clean_descs = []
    if isinstance(job_description, list):
        clean_descs = [d.strip() for d in job_description if d]
    elif job_description:
        clean_descs = [job_description.strip()]

    if not clean_titles:
        message = "At least one job title is required when creating a vendor!"
        redirect_url = str(request.url_for("list_managers", client_id=client_id)) + f"?message={message}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    try:
        # ✅ FIXED: Add manager WITHOUT status parameter (function already sets status="active" internally)
        manager = add_manager(db, client_id, name, user_id=current_user.id)
        
        # Handle different return types from add_manager
        if isinstance(manager, dict):
            manager_id = manager.get("manager_id")
            manager_name = manager.get("manager_name", name)
        else:
            manager_id = getattr(manager, "manager_id", None)
            manager_name = getattr(manager, "manager_name", name)

        if not manager_id:
            message = f"Failed to create vendor '{name}'!"
            redirect_url = str(request.url_for("list_managers", client_id=client_id)) + f"?message={message}"
            return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

        message = f"Vendor '{manager_name}' added!"

        # ✅ Add jobs for this vendor
        for idx, title in enumerate(clean_titles):
            desc = clean_descs[idx] if idx < len(clean_descs) else ""
            jobs = get_jobs_by_manager(db, manager_id)
            if any(job.job_title.lower() == title.lower() for job in jobs):
                message += f" (Job '{title}' already exists)"
            else:
                add_new_job(db, manager_id, title, desc)
                message += f" (Job '{title}' created)"

        db.commit()
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating manager or jobs: {str(e)}")
        message = f"Error creating vendor: {str(e)}"
        redirect_url = str(request.url_for("list_managers", client_id=client_id)) + f"?message={message}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    redirect_url = str(request.url_for("list_managers", client_id=client_id)) + f"?message={message}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/delete/{manager_id}", name="delete_manager_route")
def delete_manager_route(manager_id: int, db: Session = Depends(get_db)):
    m = get_manager_by_id(db, manager_id)
    if not m:
        raise HTTPException(status_code=404, detail="Manager not found")
    
    # Handle both dict and object responses
    manager_name = m.manager_name if hasattr(m, 'manager_name') else m.get('manager_name', 'Unknown')
    delete_manager(db, manager_id)
    return JSONResponse(content={"message": f"Vendor '{manager_name}' deleted successfully!"})


@router.post("/toggle/{manager_id}", name="toggle_manager_status_route")
async def toggle_manager_status_route(
    manager_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    desired = await parse_desired_status(request)
    user_id = getattr(current_user, "id", None)
    result = toggle_manager_status(db, manager_id, user_id=user_id, desired_status=desired)
    if not result:
        raise HTTPException(status_code=404, detail="Manager not found or invalid status")
    return JSONResponse(content=result)


@router.post("/edit/{manager_id}", name="edit_manager_route")
def edit_manager_route(
    manager_id: int,
    manager_name: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    name = (manager_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Manager name required")
    updated = edit_manager(db, manager_id, name, user_id=current_user.id)
    if not updated:
        raise HTTPException(status_code=404, detail="Manager not found")
    return JSONResponse(content=updated)


# ---------- Jobs for a Manager ----------

@router.get("/jobs/{manager_id}", name="vendor_jobs")
def vendor_jobs(
    request: Request, 
    manager_id: int, 
    status: str = None,  # Add status filter parameter
    db: Session = Depends(get_db)
):
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Use filtered jobs if status is provided
    if status and status != 'all':
        jobs = get_jobs_by_manager_with_status(db, manager_id, status)
    else:
        jobs = get_jobs_by_manager(db, manager_id)
    
    # Handle both dict and object responses
    if isinstance(manager, dict):
        manager_name = manager.get('manager_name', 'Unknown')
        client = manager.get('client')
        client_id = manager.get('client_id')
    else:
        manager_name = manager.manager_name
        client = manager.client
        client_id = manager.client_id

    logger.info(f"Found {len(jobs)} jobs for manager {manager_id} with status filter: {status}")

    return templates.TemplateResponse(
        "client_jobs.html",
        {
            "request": request,
            "manager": manager,
            "manager_name": manager_name,
            "client": client,
            "client_id": client_id,
            "jobs": jobs,
            "current_filter": status or 'all',  # Pass current filter to template
        },
    )


# ---------- Add a Job to an Existing Manager ----------

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
            try:
                add_new_job(db, manager_id, job_title_clean, job_description_clean)

                # ✅ FIXED: Ensure manager is active after job creation
                if hasattr(manager, "status"):
                    manager.status = "active"
                    db.add(manager)

                db.commit()
                message = f"Job '{job_title_clean}' added successfully! (Manager set to Active)"
            except Exception as e:
                db.rollback()
                logger.error(f"Error adding job: {str(e)}")
                message = f"Error adding job: {str(e)}"

    redirect_url = str(request.url_for("vendor_jobs", manager_id=manager_id)) + f"?message={message}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# ---------- Add Job from Manager List (New Endpoint) ----------

@router.post("/{manager_id}/add-job-from-list", name="add_job_from_list")
def add_job_from_list(
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
            try:
                add_new_job(db, manager_id, job_title_clean, job_description_clean)

                # ✅ FIXED: Ensure manager is active after job creation
                if hasattr(manager, "status"):
                    manager.status = "active"
                    db.add(manager)
                
                db.commit()
                message = f"Job '{job_title_clean}' added successfully! (Manager set to Active)"
            except Exception as e:
                db.rollback()
                logger.error(f"Error adding job: {str(e)}")
                message = f"Error adding job: {str(e)}"

    # Get client_id from manager
    if isinstance(manager, dict):
        client_id = manager.get('client_id')
    else:
        client_id = manager.client_id

    # Redirect back to the manager list page instead of jobs page
    redirect_url = str(request.url_for("list_managers", client_id=client_id)) + f"?message={message}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# ========== JOB MANAGEMENT ROUTES ==========

@router.post("/jobs/toggle/{job_id}", name="toggle_job_status_route")
async def toggle_job_status_route(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Toggle job status between active and inactive
    """
    desired = await parse_desired_status(request)
    user_id = getattr(current_user, "id", None)
    result = toggle_job_status_single(db, job_id, user_id=user_id, desired_status=desired)
    if not result:
        raise HTTPException(status_code=404, detail="Job not found or invalid status")
    return JSONResponse(content=result)


@router.post("/jobs/delete/{job_id}", name="delete_job_route")
def delete_job_route(
    job_id: int, 
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Delete a job
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_title = job.job_title
    success = delete_job_single(db, job_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete job")
    
    return JSONResponse(content={"message": f"Job '{job_title}' deleted successfully!"})


@router.post("/jobs/edit/{job_id}", name="edit_job_route")
def edit_job_route(
    job_id: int,
    job_title: str = Form(...),
    job_description: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Edit job title and description
    """
    title_clean = (job_title or "").strip()
    description_clean = (job_description or "").strip()
    
    if not title_clean:
        raise HTTPException(status_code=400, detail="Job title required")
    
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Update job
    job.job_title = title_clean
    job.job_description = description_clean
    job.updated_by = current_user.id
    job.updated_at = datetime.now(IST)
    
    db.add(job)
    db.commit()
    db.refresh(job)
    
    return JSONResponse(content={
        "message": f"Job updated to '{title_clean}'",
        "job_title": job.job_title,
        "job_description": job.job_description
    })