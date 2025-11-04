# landing_page_app/routers/vendors.py
# Purpose: preserve all existing behavior, but make user activity logs human-friendly
# (use user.full_name, manager.manager_name, client.client_name, job.job_title in logs).

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
from landing_page_app.models.managers import Manager
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
from landing_page_app.routers.utils.jobs_utils import (
    get_jobs_by_manager,
    add_new_job,
    toggle_job_status_single,
    delete_job_single,
    get_jobs_by_manager_with_status,
)
from landing_page_app.models.user import User
from landing_page_app.models.log import add_user_log

router = APIRouter(prefix="/clients/vendors", tags=["Client Vendors"])
templates = Jinja2Templates(directory="landing_page_app/templates")
logger = logging.getLogger(__name__)

# UTC timezone
UTC = ZoneInfo("Asia/Kolkata")


def get_client_or_404(db: Session, client_id: int) -> Client:
    c = db.query(Client).filter(Client.client_id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


async def parse_desired_status(request: Request) -> Optional[str]:
    """
    Accepts JSON or form or query param "status"/"new_status"/"desired".
    Returns 'active'/'inactive' or None.
    """
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


@router.get("/client/{client_id}", name="list_managers")
def list_managers_page(
    request: Request,
    client_id: int,
    db: Session = Depends(get_db),
    message: str = "",
    user: User = Depends(get_current_user),
):
    """
    Show managers/vendors for a client. Keeps behavior identical but ensures template
    receives manager_name and jobs in a consistent structure.
    """
    client = get_client_or_404(db, client_id)
    managers = get_managers_for_client(db, client_id)

    managers_with_jobs = []
    for manager in managers:
        # If the util returned a dict (it may include readable names already), use it directly.
        if isinstance(manager, dict):
            # Ensure jobs are filled (fetch if not present)
            jobs = manager.get("jobs") or get_jobs_by_manager(db, manager.get("manager_id"))
            managers_with_jobs.append({
                "manager_id": manager.get("manager_id"),
                "manager_name": manager.get("manager_name") or f"Manager {manager.get('manager_id', '')}",
                "status": manager.get("status", "active"),
                "client_id": client_id,
                "jobs": jobs,
                "created_by": manager.get("created_by", None),
                "created_by_name": manager.get("created_by_name", "N/A"),
                "created_at": manager.get("created_at", None),
                "updated_by": manager.get("updated_by", None),
                "updated_by_name": manager.get("updated_by_name", "N/A"),
                "updated_at": manager.get("updated_at", None),
            })
            continue

        # Otherwise the util returned an ORM Manager object — normalize and enrich with names
        manager_obj = manager if isinstance(manager, Manager) else get_manager_by_id(db, manager.get("manager_id"))
        if not manager_obj:
            continue

        jobs = get_jobs_by_manager(db, manager_obj.manager_id)

        # Try to resolve readable user names from user IDs
        created_by_id = getattr(manager_obj, "created_by", None)
        updated_by_id = getattr(manager_obj, "updated_by", None)

        created_by_name = None
        updated_by_name = None
        if created_by_id is not None:
            u = db.query(User).filter(User.id == created_by_id).first()
            created_by_name = getattr(u, "full_name", None) or getattr(u, "email", None) if u else "N/A"
        if updated_by_id is not None:
            u2 = db.query(User).filter(User.id == updated_by_id).first()
            updated_by_name = getattr(u2, "full_name", None) or getattr(u2, "email", None) if u2 else "N/A"

        managers_with_jobs.append({
            "manager_id": getattr(manager_obj, "manager_id", None),
            "manager_name": getattr(manager_obj, "manager_name", None) or f"Manager {getattr(manager_obj, 'manager_id', '')}",
            "status": getattr(manager_obj, "status", "active"),
            "client_id": client_id,
            "jobs": jobs,
            "created_by": created_by_id,
            "created_by_name": created_by_name or "N/A",
            "created_at": getattr(manager_obj, "created_at", None),
            "updated_by": updated_by_id,
            "updated_by_name": updated_by_name or "N/A",
            "updated_at": getattr(manager_obj, "updated_at", None),
        })


    return templates.TemplateResponse(
        "managers.html",
        {
            "request": request,
            "client": client,
            "managers": managers_with_jobs,
            "message": message,
            "get_jobs_by_manager": get_jobs_by_manager,
            "user": user,
        },
    )


@router.post("/client/{client_id}/add", name="add_new_manager")
def add_new_manager(
    request: Request,
    client_id: int,
    manager_name: str = Form(...),
    job_title: List[str] = Form(...),
    job_description: List[str] = Form([]),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a manager (vendor) and optional jobs. Logging updated to include names.
    """
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

    try:
        manager = add_manager(db, client_id, name, user_id=getattr(current_user, "id", None))
        # ensure manager is refreshed / object-like if util returned dict
        if not hasattr(manager, "manager_id"):
            # try to fetch object
            mid = manager.get("manager_id") if isinstance(manager, dict) else None
            manager = get_manager_by_id(db, mid) if mid else manager

        # Log creation with user name and client/manager names
        try:
            uname = getattr(current_user, "full_name", getattr(current_user, "email", "Unknown User"))
            mname = getattr(manager, "manager_name", name)
            cname = getattr(client, "client_name", f"Client {client_id}")
            add_user_log(db, getattr(current_user, "id", None), f"{uname} CREATED MANAGER '{mname}' for CLIENT '{cname}'", commit=True)
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

        # create jobs if any
        clean_titles = []
        if isinstance(job_title, list):
            clean_titles = [t.strip() for t in job_title if t and t.strip()]
        elif job_title:
            clean_titles = [(job_title or "").strip()]

        clean_descs = []
        if isinstance(job_description, list):
            clean_descs = [d.strip() for d in job_description if d]
        elif job_description:
            clean_descs = [(job_description or "").strip()]

        for idx, title in enumerate(clean_titles):
            t = title
            desc = clean_descs[idx] if idx < len(clean_descs) else ""
            existing_jobs = get_jobs_by_manager(db, getattr(manager, "manager_id", None))
            if any(getattr(j, "job_title", "").lower() == t.lower() for j in (existing_jobs or [])):
                message += f" (Job '{t}' already exists)"
                continue
            add_new_job(db, getattr(manager, "manager_id", None), t, desc, created_by=getattr(current_user, "id", None))
            try:
                uname = getattr(current_user, "full_name", getattr(current_user, "email", "Unknown User"))
                mname = getattr(manager, "manager_name", name)
                add_user_log(db, getattr(current_user, "id", None), f"{uname} CREATED JOB '{t}' under MANAGER '{mname}'", commit=True)
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass

        db.commit()
        message = message or f"Vendor '{name}' added!"
    except Exception as e:
        db.rollback()
        logger.exception("Failed to add manager or jobs: %s", e)
        message = f"Error creating vendor: {str(e)}"

    redirect_url = str(request.url_for("list_managers", client_id=client_id)) + f"?message={message}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/delete/{manager_id}", name="delete_manager_route")
def delete_manager_route(manager_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    m = get_manager_by_id(db, manager_id)
    if not m:
        raise HTTPException(status_code=404, detail="Manager not found")

    # get client name where possible
    client = db.query(Client).filter(Client.client_id == getattr(m, "client_id", None)).first()
    client_name = getattr(client, "client_name", f"Client {getattr(m, 'client_id', '')}")

    manager_name = getattr(m, "manager_name", f"Manager {manager_id}")

    # Remove manager (util handles cascade)
    delete_manager(db, manager_id)
    try:
        uname = getattr(current_user, "full_name", getattr(current_user, "email", "Unknown User"))
        add_user_log(db, getattr(current_user, "id", None), f"{uname} DELETED MANAGER '{manager_name}' from CLIENT '{client_name}'", commit=True)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    return JSONResponse(content={"message": f"Vendor '{manager_name}' deleted successfully!"})


@router.post("/toggle/{manager_id}", name="toggle_manager_status_route")
async def toggle_manager_status_route(
    manager_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    desired = await parse_desired_status(request)
    result = toggle_manager_status(db, manager_id, user_id=getattr(current_user, "id", None), desired_status=desired)
    m = get_manager_by_id(db, manager_id)
    client = db.query(Client).filter(Client.client_id == getattr(m, "client_id", None)).first()

    state = "ACTIVATED" if result.get("new_status") == "active" else "DEACTIVATED"
    try:
        uname = getattr(current_user, "full_name", getattr(current_user, "email", "Unknown User"))
        mname = getattr(m, "manager_name", f"Manager {manager_id}")
        cname = getattr(client, "client_name", f"Client {getattr(m, 'client_id', '')}")
        add_user_log(db, getattr(current_user, "id", None), f"{uname} {state} MANAGER '{mname}' of CLIENT '{cname}'", commit=True)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    return JSONResponse(content=result)


@router.post("/edit/{manager_id}", name="edit_manager_route")
def edit_manager_route(
    manager_id: int,
    manager_name: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not manager_name or not manager_name.strip():
        raise HTTPException(status_code=400, detail="Manager name required")

    m = get_manager_by_id(db, manager_id)
    if not m:
        raise HTTPException(status_code=404, detail="Manager not found")

    old_name = getattr(m, "manager_name", None)
    updated = edit_manager(db, manager_id, manager_name.strip(), user_id=getattr(current_user, "id", None))

    # refresh manager object after update
    m = get_manager_by_id(db, manager_id)
    client = db.query(Client).filter(Client.client_id == getattr(m, "client_id", None)).first()
    client_name = getattr(client, "client_name", f"Client {getattr(m, 'client_id', '')}")
    try:
        uname = getattr(current_user, "full_name", getattr(current_user, "email", "Unknown User"))
        add_user_log(db, getattr(current_user, "id", None), f"{uname} EDITED MANAGER '{old_name}' → '{getattr(m, 'manager_name', '')}' for CLIENT '{client_name}'", commit=True)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    return JSONResponse(content=updated)


@router.get("/jobs/{manager_id}", name="vendor_jobs")
def vendor_jobs(
    request: Request,
    manager_id: int,
    status: str = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Render jobs for a manager. Keeps behavior identical; passes manager and jobs to template.
    """
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Vendor not found")

    if status and status != "all":
        jobs = get_jobs_by_manager_with_status(db, manager_id, status)
    else:
        jobs = get_jobs_by_manager(db, manager_id)

    manager_name = getattr(manager, "manager_name", f"Manager {manager_id}")
    client = getattr(manager, "client", None)
    client_id = getattr(manager, "client_id", None)

    return templates.TemplateResponse(
        "client_jobs.html",
        {
            "request": request,
            "manager": manager,
            "manager_name": manager_name,
            "client": client,
            "client_id": client_id,
            "jobs": jobs,
            "current_filter": status or "all",
            "user": user,
        },
    )


@router.post("/{manager_id}/add-job", name="add_job")
def add_job(
    request: Request,
    manager_id: int,
    job_title: str = Form(...),
    job_description: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
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
        if any(getattr(job, "job_title", "").lower() == job_title_clean.lower() for job in (jobs or [])):
            message = f"Job '{job_title_clean}' already exists!"
        else:
            try:
                add_new_job(db, manager_id, job_title_clean, job_description_clean, created_by=getattr(current_user, "id", None))
                # log creation with names
                try:
                    uname = getattr(current_user, "full_name", getattr(current_user, "email", "Unknown User"))
                    mname = getattr(manager, "manager_name", f"Manager {manager_id}")
                    add_user_log(db, getattr(current_user, "id", None), f"{uname} CREATED JOB '{job_title_clean}' under MANAGER '{mname}'", commit=True)
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass

                # Ensure manager active if attribute exists
                if hasattr(manager, "status"):
                    manager.status = "active"
                    db.add(manager)

                db.commit()
                message = f"Job '{job_title_clean}' added successfully! (Manager set to Active)"
            except Exception as e:
                db.rollback()
                logger.exception("Error adding job: %s", e)
                message = f"Error adding job: {str(e)}"

    redirect_url = str(request.url_for("vendor_jobs", manager_id=manager_id)) + f"?message={message}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{manager_id}/add-job-from-list", name="add_job_from_list")
def add_job_from_list(
    request: Request,
    manager_id: int,
    job_title: str = Form(...),
    job_description: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
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
        if any(getattr(j, "job_title", "").lower() == job_title_clean.lower() for j in (jobs or [])):
            message = f"Job '{job_title_clean}' already exists!"
        else:
            try:
                add_new_job(db, manager_id, job_title_clean, job_description_clean, created_by=getattr(current_user, "id", None))
                try:
                    uname = getattr(current_user, "full_name", getattr(current_current_user := current_user, "email", "Unknown User"))
                    mname = getattr(manager, "manager_name", f"Manager {manager_id}")
                    add_user_log(db, getattr(current_user, "id", None), f"{uname} CREATED JOB '{job_title_clean}' under MANAGER '{mname}'", commit=True)
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass

                if hasattr(manager, "status"):
                    manager.status = "active"
                    db.add(manager)

                db.commit()
                message = f"Job '{job_title_clean}' added successfully! (Manager set to Active)"
            except Exception as e:
                db.rollback()
                logger.exception("Error adding job from list: %s", e)
                message = f"Error adding job: {str(e)}"

    client_id = getattr(manager, "client_id", None)
    redirect_url = str(request.url_for("list_managers", client_id=client_id)) + f"?message={message}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/jobs/toggle/{job_id}", name="toggle_job_status_route")
async def toggle_job_status_route(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    desired = await parse_desired_status(request)
    result = toggle_job_status_single(db, job_id, user_id=getattr(current_user, "id", None), desired_status=desired)
    job = db.query(Job).filter(Job.job_id == job_id).first()
    m = db.query(Manager).filter(Manager.manager_id == getattr(job, "manager_id", None)).first()

    state = "ACTIVATED" if result.get("new_status") == "active" else "DEACTIVATED"
    try:
        uname = getattr(current_current_user := current_user, "full_name", getattr(current_current_user, "email", "Unknown User"))
        jtitle = getattr(job, "job_title", f"Job {job_id}")
        mname = getattr(m, "manager_name", f"Manager {getattr(job, 'manager_id', '')}")
        add_user_log(db, getattr(current_current_user, "id", None), f"{uname} {state} JOB '{jtitle}' under MANAGER '{mname}'", commit=True)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    return JSONResponse(content=result)


@router.post("/jobs/delete/{job_id}", name="delete_job_route")
def delete_job_route(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    m = db.query(Manager).filter(Manager.manager_id == getattr(job, "manager_id", None)).first()
    mname = getattr(m, "manager_name", f"Manager {getattr(job, 'manager_id', '')}")
    jtitle = getattr(job, "job_title", f"Job {job_id}")

    delete_job_single(db, job_id)
    try:
        uname = getattr(current_user, "full_name", getattr(current_current_user := current_user, "email", "Unknown User"))
        add_user_log(db, getattr(current_current_user, "id", None), f"{uname} DELETED JOB '{jtitle}' under MANAGER '{mname}'", commit=True)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    return JSONResponse(content={"message": f"Job '{jtitle}' deleted successfully!"})


@router.post("/jobs/edit/{job_id}", name="edit_job_route")
def edit_job_route(
    job_id: int,
    job_title: str = Form(...),
    job_description: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    m = db.query(Manager).filter(Manager.manager_id == getattr(job, "manager_id", None)).first()
    mname = getattr(m, "manager_name", f"Manager {getattr(job, 'manager_id', '')}")
    old_title = getattr(job, "job_title", "")

    job.job_title = (job_title or "").strip()
    job.job_description = (job_description or "").strip()
    job.updated_by = getattr(current_current_user := current_user, "id", None)
    job.updated_at = datetime.now(UTC)
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        uname = getattr(current_current_user, "full_name", getattr(current_current_user, "email", "Unknown User"))
        add_user_log(db, getattr(current_current_user, "id", None), f"{uname} EDITED JOB '{old_title}' → '{job.job_title}' under MANAGER '{mname}'", commit=True)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    return JSONResponse(content={
        "message": f"Job updated",
        "job_title": job.job_title,
        "job_description": job.job_description
    })
