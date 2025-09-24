from fastapi import APIRouter, Request, Form, HTTPException, Depends, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List

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
)

router = APIRouter(prefix="/vendors", tags=["Vendors"])
templates = Jinja2Templates(directory="landing_page_app/templates")


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
    return templates.TemplateResponse(
        "managers.html",
        {"request": request, "client": client, "managers": managers, "message": message},
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
    clean_titles = [t.strip() for t in job_title if t.strip()]
    clean_descs = [d.strip() for d in job_description]

    if not clean_titles:
        message = "At least one job title is required when creating a vendor!"
        redirect_url = str(request.url_for("list_managers", client_id=client_id)) + f"?message={message}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    # ✅ Add manager
    manager = add_manager(db, client_id, name, user_id=current_user.id)

    # If add_manager returns a dict, get manager_id from dict
    manager_id = manager.get("manager_id") if isinstance(manager, dict) else getattr(manager, "manager_id", None)

    if not manager_id:
        message = f"Failed to create vendor '{name}'!"
        redirect_url = str(request.url_for("list_managers", client_id=client_id)) + f"?message={message}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    message = f"Vendor '{name}' added!"

    # ✅ Add jobs for this vendor
    for idx, title in enumerate(clean_titles):
        desc = clean_descs[idx] if idx < len(clean_descs) else ""
        jobs = get_jobs_by_manager(db, manager_id)
        if any(job.job_title.lower() == title.lower() for job in jobs):
            message += f" (Job '{title}' already exists)"
        else:
            add_new_job(db, manager_id, title, desc,)
            message += f" (Job '{title}' created)"

    redirect_url = str(request.url_for("list_managers", client_id=client_id)) + f"?message={message}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/delete/{manager_id}", name="delete_manager_route")
def delete_manager_route(manager_id: int, db: Session = Depends(get_db)):
    m = get_manager_by_id(db, manager_id)
    if not m:
        raise HTTPException(status_code=404, detail="Manager not found")
    delete_manager(db, manager_id)
    return JSONResponse(content={"message": f"Vendor '{m.manager_name}' deleted successfully!"})


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
def vendor_jobs(request: Request, manager_id: int, db: Session = Depends(get_db)):
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Vendor not found")

    jobs = db.query(Job).filter(Job.manager_id == manager_id).all()

    return templates.TemplateResponse(
        "client_jobs.html",
        {
            "request": request,
            "manager": manager,
            "client": manager.client,
            "jobs": jobs,
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
            add_new_job(db, manager_id, job_title_clean, job_description_clean)
            message = f"Job '{job_title_clean}' added successfully!"

    redirect_url = str(request.url_for("vendor_jobs", manager_id=manager_id)) + f"?message={message}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
