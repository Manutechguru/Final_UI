# landing_page_app/routers/clients/base.py
from fastapi import APIRouter, Request, Form, HTTPException, Depends, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
from zoneinfo import ZoneInfo

from landing_page_app.database import get_db
from landing_page_app.models.clients import Client
from landing_page_app.models.jobs import Job
from landing_page_app.models.managers import Manager
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.routers.utils.clients_utils import toggle_client_status

# NEW: user injection imports (minimal)
from landing_page_app.models.user import User
from landing_page_app.routers.auth import get_current_user

# NEW: logging helper
from landing_page_app.models.log import add_user_log

# Define IST timezone
IST = ZoneInfo("Asia/Kolkata")

# ------------------------------
# Router setup with prefix
# ------------------------------
router = APIRouter(prefix="/clients", tags=["Clients"])
templates = Jinja2Templates(directory="landing_page_app/templates")

# ------------------------------
# 1. List all clients
# ------------------------------
@router.get("/new-arrivals", name="new_arrivals_page")
def new_arrivals_page(
    request: Request,
    db: Session = Depends(get_db),
    message: str = "",
    user: User = Depends(get_current_user),   # <-- added
):
    clients = db.query(Client).order_by(Client.created_at.desc()).all()
    active_count = db.query(Client).filter(Client.status == "active").count()
    inactive_count = db.query(Client).filter(Client.status == "inactive").count()

    return templates.TemplateResponse(
        "new_arrivals.html",
        {
            "request": request,
            "clients": clients,
            "active_count": active_count,
            "inactive_count": inactive_count,
            "message": message,
            "user": user,   # <-- added
        },
    )

# ------------------------------
# 2. Add New Client (with optional Vendor and Job)
# ------------------------------
@router.post("/new-arrivals")
def add_new_client(
    request: Request,
    client_name: str = Form(...),
    manager_name: str = Form(None),
    job_title: str = Form(None),
    job_description: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),   # <-- added to record actor
):
    client_name = (client_name or "").strip()
    manager_name = (manager_name or "").strip()
    job_title = (job_title or "").strip()
    job_description = (job_description or "").strip()
    
    # actor name fallback
    actor = getattr(user, "full_name", None) or getattr(user, "email", None) or getattr(user, "id", None)

    message_parts = []

    if not client_name:
        message_parts.append("Client name is required!")
        redirect_url = str(request.url_for("new_arrivals_page")) + f"?message={' '.join(message_parts)}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    # Check if client exists
    existing_client = db.query(Client).filter(Client.client_name == client_name).first()
    if existing_client:
        message_parts.append(f"Client '{client_name}' already exists!")
        client = existing_client
    else:
        # Create client
        client = Client(client_name=client_name, created_at=datetime.now(IST), status="active")
        db.add(client)
        client.created_by = user.id
        db.commit()
        db.refresh(client)
        message_parts.append(f"Client '{client_name}' added successfully!")
        # log creation (commit immediately because we've already committed client)
        try:
            add_user_log(db, user.id, f"{actor} CREATED CLIENT {client.client_name}", commit=True)
        except Exception:
            # fail-safe: do not break main flow on logging failure
            try:
                db.rollback()
            except Exception:
                pass

    # Optional: Add manager/vendor
    if manager_name:
        existing_manager = db.query(Manager).filter(
            Manager.client_id == client.client_id,
            Manager.manager_name == manager_name
        ).first()
        if existing_manager:
            message_parts.append(f"Vendor '{manager_name}' already exists!")
            manager = existing_manager
        else:
            manager = Manager(client_id=client.client_id, manager_name=manager_name, created_at=datetime.now(IST))
            manager.created_by = user.id
            db.add(manager)
            db.commit()
            db.refresh(manager)
            message_parts.append(f"Vendor '{manager_name}' added!")
            # log manager creation (commit immediately)
            try:
                add_user_log(db, user.id, f"{actor} CREATED MANAGER {manager.manager_name} for CLIENT {client.client_name}", commit=True)
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass

        # Optional: Add job under this manager
        if job_title:
            existing_jobs = db.query(Job).filter(Job.manager_id == manager.manager_id).all()
            if any(job.job_title.lower() == job_title.lower() for job in existing_jobs):
                message_parts.append(f"Job '{job_title}' already exists!")
            else:
                job = Job(
                    manager_id=manager.manager_id,
                    job_title=job_title,
                    job_description=job_description,
                    created_at=datetime.now(IST),
                    status="active"
                )
                job.created_by = user.id
                db.add(job)
                db.commit()
                message_parts.append(f"Job '{job_title}' added successfully!")
                # log job creation (commit immediately)
                db.refresh(job)
                try:
                    add_user_log(
                        db,
                        user.id,
                        f"{actor} CREATED JOB {job.job_title} under MANAGER {manager.manager_name} for CLIENT {client.client_name}",
                        commit=True
                    )
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass

    redirect_url = str(request.url_for("new_arrivals_page")) + f"?message={' | '.join(message_parts)}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

# ------------------------------
# 3. Delete a Client
# ------------------------------
@router.post("/delete/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Capture name for logging before delete
    client_name_for_log = client.client_name

    # Delete related jobs via managers
    jobs = db.query(Job).filter(Job.manager_id.in_([m.manager_id for m in client.managers])).all()
    job_ids = [job.job_id for job in jobs]

    if job_ids:
        db.query(CandidateJDMapping).filter(CandidateJDMapping.jd_id.in_(job_ids)).delete(synchronize_session=False)
        db.query(Job).filter(Job.job_id.in_(job_ids)).delete(synchronize_session=False)

    # Delete managers
    db.query(Manager).filter(Manager.client_id == client_id).delete(synchronize_session=False)

    # Delete client
    db.delete(client)
    db.commit()

    # actor name fallback
    actor = getattr(user, "full_name", None) or getattr(user, "email", None) or getattr(user, "id", None)

    # Log deletion (commit immediately)
    try:
        add_user_log(db, user.id, f"{actor} DELETED CLIENT {client_name_for_log}", commit=True)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    return JSONResponse(content={"message": f"Client '{client_name_for_log}' and related records deleted successfully!"})

# ------------------------------
# 4. Toggle Client Status
# ------------------------------
@router.post("/toggle/{client_id}")
def toggle_client_status_api(client_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = toggle_client_status(db, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # actor name fallback
    actor = getattr(user, "full_name", None) or getattr(user, "email", None) or getattr(user, "id", None)

    # Log activation/deactivation (commit immediately)
    state = "ACTIVATED" if client.status == "active" else "DEACTIVATED"
    try:
        add_user_log(db, user.id, f"{actor} {state} CLIENT {client.client_name}", commit=True)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    return {"client_id": client.client_id, "new_status": client.status}

# ------------------------------
# 5. Client Statistics (JSON)
# ------------------------------
@router.get("/stats")
def get_client_stats(db: Session = Depends(get_db)):
    return JSONResponse(
        content={
            "total_clients": db.query(Client).count(),
            "active_clients": db.query(Client).filter(Client.status == "active").count(),
            "inactive_clients": db.query(Client).filter(Client.status == "inactive").count(),
            "total_jobs": db.query(Job).count(),
            "active_jobs": db.query(Job).filter(Job.status == "active").count(),
            "inactive_jobs": db.query(Job).filter(Job.status == "inactive").count(),
        }
    )

# ------------------------------
# 6. View Client and Jobs
# ------------------------------
@router.get("/{client_id}", name="client_detail_page")
def client_detail(
    request: Request,
    client_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),   # <-- added
):
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Load jobs via managers
    jobs = []
    for manager in client.managers:
        jobs.extend(db.query(Job).filter(Job.manager_id == manager.manager_id).order_by(Job.created_at.desc()).all())

    return templates.TemplateResponse(
        "client_jobs.html",
        {"request": request, "client": client, "jobs": jobs, "user": user}  # <-- added user
    )

# ------------------------------
# 7. Edit Client
# ------------------------------
@router.post("/edit/{client_id}")
def edit_client(
    client_id: int,
    new_name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    existing_client = db.query(Client).filter(
        Client.client_name == new_name,
        Client.client_id != client_id
    ).first()
    if existing_client:
        raise HTTPException(status_code=400, detail=f"Client '{new_name}' already exists")

    old_name = client.client_name
    client.client_name = new_name
    client.updated_at = datetime.now(IST)
    client.updated_by = user.id
    db.commit()
    db.refresh(client)

    # actor name fallback
    actor = getattr(user, "full_name", None) or getattr(user, "email", None) or getattr(user, "id", None)

    # Log edit (commit immediately)
    try:
        add_user_log(db, user.id, f"{actor} EDITED CLIENT {old_name} → {client.client_name}", commit=True)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    return {"message": f"Client '{new_name}' updated successfully!"}
# ------------------------------
# 8. Client quick details (for popup modal)
# ------------------------------
@router.get("/details/{client_id}")
def get_client_details(
    client_id: int,
    db: Session = Depends(get_db),
):
    # join to get full name of created_by & updated_by
    from landing_page_app.models.user import User

    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # fetch created_by / updated_by usernames if present
    created_by_name = None
    if client.created_by:
        created_user = db.query(User).filter(User.id == client.created_by).first()
        if created_user:
            created_by_name = created_user.full_name

    updated_by_name = None
    if client.updated_by:
        updated_user = db.query(User).filter(User.id == client.updated_by).first()
        if updated_user:
            updated_by_name = updated_user.full_name

    return {
        "client_name": client.client_name,
        "created_by": created_by_name,
        "created_at": client.created_at.strftime("%Y-%m-%d %H:%M:%S") if client.created_at else None,
        "updated_by": updated_by_name,
        "updated_at": client.updated_at.strftime("%Y-%m-%d %H:%M:%S") if client.updated_at else None,
    }