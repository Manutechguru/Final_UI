from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import joinedload
from sqlalchemy import desc
from landing_page_app.database import SessionLocal
from landing_page_app.models.managers import Manager
from landing_page_app.models.clients import Client
from fastapi.templating import Jinja2Templates
from typing import Optional

router = APIRouter(prefix="/clients/all_managers", tags=["All Managers"])
templates = Jinja2Templates(directory="landing_page_app/templates")


@router.get("")
@router.get("/")
def all_managers_page(request: Request):
    """Render the All Managers HTML page."""
    with SessionLocal() as db:
        clients = db.query(Client).order_by(Client.client_name).all()
    return templates.TemplateResponse("all_managers.html", {"request": request, "clients": clients})


@router.get("/data")
def get_all_managers_data(
    client_id: Optional[int] = Query(None),
    recent: Optional[bool] = Query(False, description="Sort by most recently created")
):
    """Return JSON list of managers (optionally filtered by client)."""
    with SessionLocal() as db:
        query = db.query(Manager).options(joinedload(Manager.client))

        if client_id is not None:
            query = query.filter(Manager.client_id == client_id)

        # Sorting if model has created_at (not required)
        try:
            if recent:
                query = query.order_by(desc(Manager.created_at))
            else:
                query = query.order_by(Manager.created_at)
        except Exception:
            # Model might not have created_at — ignore ordering then
            pass

        managers = query.all()

        result = []
        for m in managers:
            manager_email = getattr(m, "manager_email", None) or getattr(m, "email", None) or "-"
            created = getattr(m, "created_at", None)
            created_str = created.strftime("%Y-%m-%d") if created is not None else "-"
            result.append({
                "manager_id": m.manager_id,
                "manager_name": m.manager_name,
                "manager_email": manager_email,
                "client_name": m.client.client_name if getattr(m, "client", None) else "-",
                "client_id": m.client.client_id if getattr(m, "client", None) else None,
                "status": getattr(m, "status", "Active") if hasattr(m, "status") else "Active",
                "created_at": created_str,
                "link": f"/clients/manager/{m.manager_id}" if getattr(m, "manager_id", None) else "#"
            })

    return {"managers": result}


@router.delete("/{manager_id}")
def delete_manager(manager_id: int):
    """Delete a manager by ID."""
    with SessionLocal() as db:
        manager = db.query(Manager).filter(Manager.manager_id == manager_id).first()
        if not manager:
            return JSONResponse(status_code=404, content={"detail": "Manager not found"})
        db.delete(manager)
        db.commit()
    return JSONResponse(status_code=200, content={"detail": "Manager deleted"})


@router.post("/edit/{manager_id}")
async def update_manager(request: Request, manager_id: int):
    """Update manager fields submitted from the edit modal."""
    form = await request.form()
    name = form.get("manager_name")
    email = form.get("manager_email")
    client_id = form.get("client_id")
    status = form.get("status")

    with SessionLocal() as db:
        manager = db.query(Manager).filter(Manager.manager_id == manager_id).first()
        if not manager:
            raise HTTPException(status_code=404, detail="Manager not found")

        if name is not None:
            manager.manager_name = name.strip()
        if email is not None and hasattr(manager, "manager_email"):
            manager.manager_email = email.strip()
        elif email is not None and hasattr(manager, "email"):
            manager.email = email.strip()

        if client_id:
            try:
                manager.client_id = int(client_id)
            except ValueError:
                pass

        if status is not None and hasattr(manager, "status"):
            manager.status = status

        db.add(manager)
        db.commit()

    return RedirectResponse(url="/clients/all_managers", status_code=303)
