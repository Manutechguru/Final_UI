from fastapi import APIRouter, Request, Form, HTTPException, Depends, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

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

router = APIRouter(prefix="/vendors", tags=["Vendors"])
templates = Jinja2Templates(directory="landing_page_app/templates")


def get_client_or_404(db: Session, client_id: int) -> Client:
    c = db.query(Client).filter(Client.client_id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


async def parse_desired_status(request: Request) -> Optional[str]:
    """
    Try to extract desired 'status' from:
      1) JSON body (status/new_status/desired)
      2) form body (status/new_status)
      3) query param ?status=
    Returns 'active'|'inactive' or None (meaning toggle).
    """
    desired = None
    try:
        raw = await request.body()
    except Exception:
        raw = b""

    if raw:
        # try JSON
        try:
            payload = await request.json()
            if isinstance(payload, dict):
                desired = payload.get("status") or payload.get("new_status") or payload.get("desired")
        except Exception:
            # try form
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

    return None  # means toggle


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
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    client = get_client_or_404(db, client_id)
    name = (manager_name or "").strip()
    if not name:
        message = "Manager name is required!"
    elif manager_exists(db, client_id, name):
        message = f"Vendor '{name}' already exists!"
    else:
        add_manager(db, client_id, name, user_id=current_user.id)
        message = f"Vendor '{name}' added!"
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
    # Fetch manager
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Fetch jobs for this manager
    jobs = db.query(Job).filter(Job.manager_id == manager_id).all()

    return templates.TemplateResponse(
        "client_jobs.html",
        {
            "request": request,
            "manager": manager,   # ✅ Correctly passing manager
            "client": manager.client,  # ✅ Pass the linked client too
            "jobs": jobs,
        },
    )

