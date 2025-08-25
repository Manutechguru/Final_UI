# landing_page_app/routers/vendors.py
from fastapi import APIRouter, Request, Form, HTTPException, Depends, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from landing_page_app.database import get_db
from landing_page_app.models.clients import Client
from landing_page_app.routers.utils.vendors_utils import (
    get_manager_by_id,
    get_managers_for_client,
    add_manager,
    delete_manager,
    toggle_manager_status,
    manager_exists  # <-- new helper to check duplicates
)

# ------------------------------
# Router setup
# ------------------------------
router = APIRouter(prefix="/vendors", tags=["Vendors"])
templates = Jinja2Templates(directory="landing_page_app/templates")

# ------------------------------
# 1. List all managers under a client
# ------------------------------
@router.get("/client/{client_id}", name="list_managers")
def list_managers_page(
    request: Request, 
    client_id: int, 
    db: Session = Depends(get_db), 
    message: str = ""
):
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    managers = get_managers_for_client(db, client_id)
    return templates.TemplateResponse(
        "managers.html",
        {
            "request": request,
            "client": client,
            "managers": managers,
            "message": message,
        }
    )

# ------------------------------
# 2. Add a new manager under a client
# ------------------------------
@router.post("/client/{client_id}/add")
def add_new_manager(
    request: Request,
    client_id: int,
    manager_name: str = Form(...),
    db: Session = Depends(get_db)
):
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    manager_name = manager_name.strip()
    message = ""

    if not manager_name:
        message = "Manager name is required!"
    else:
        # Check if manager already exists under this client
        if manager_exists(db, client_id, manager_name):
            message = f"Manager '{manager_name}' already exists under this client!"
        else:
            add_manager(db, client_id, manager_name)
            message = f"Manager '{manager_name}' added successfully!"

    redirect_url = str(request.url_for("list_managers", client_id=client_id)) + f"?message={message}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

# ------------------------------
# 3. Delete a manager
# ------------------------------
@router.post("/delete/{manager_id}")
def delete_manager_route(manager_id: int, db: Session = Depends(get_db)):
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")

    delete_manager(db, manager_id)
    return JSONResponse(content={"message": f"Manager '{manager.manager_name}' and related jobs deleted successfully!"})

# ------------------------------
# 4. Toggle manager status
# ------------------------------
@router.post("/toggle/{manager_id}")
def toggle_manager_status_route(manager_id: int, db: Session = Depends(get_db)):
    manager = toggle_manager_status(db, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")

    return {"manager_id": manager.manager_id, "new_status": manager.status}
