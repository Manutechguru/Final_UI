from fastapi import APIRouter, Request, Form, HTTPException, Depends, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from landing_page_app.database import get_db
from landing_page_app.models.clients import Client
from landing_page_app.models.jobs import Job
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from zoneinfo import ZoneInfo
from landing_page_app.routers.utils.clients_utils import toggle_client_status
# Define IST timezone once
IST = ZoneInfo("Asia/Kolkata")

# ------------------------------
# Router setup with prefix
# ------------------------------
router = APIRouter(prefix="/clients",tags=["Clients"])  # <-- prefix for all client routes

# Templates folder
templates = Jinja2Templates(directory="landing_page_app/templates")

# ------------------------------
# 1. List all clients (New Arrivals Page)
# ------------------------------
@router.get("/new-arrivals", name="new_arrivals_page")
def new_arrivals_page(request: Request, db: Session = Depends(get_db), message: str = ""):
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
        },
    )

# ------------------------------
# 2. Add a New Client (POST)
# ------------------------------
@router.post("/new-arrivals")
def add_new_client(request: Request, client_name: str = Form(...), db: Session = Depends(get_db)):
    client_name = client_name.strip()
    message = ""

    if not client_name:
        message = "Client name is required!"
    else:
        existing_client = db.query(Client).filter(Client.client_name == client_name).first()
        if existing_client:
            message = f"Client '{client_name}' already exists!"
        else:
            new_client = Client(
                client_name=client_name,
                created_at=datetime.now(IST),
                status="active"
            )
            db.add(new_client)
            db.commit()
            db.refresh(new_client)
            message = f"Client '{client_name}' added successfully!"

    # Convert URL object to string before concatenation
    redirect_url = str(request.url_for("new_arrivals_page")) + f"?message={message}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# ------------------------------
# 3. Delete a Client
# ------------------------------
@router.post("/delete/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)):
    # Get client
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Step 1: Get all jobs related to this client via managers (adjust if needed)
    jobs = db.query(Job).filter(Job.manager_id.in_(
        [manager.manager_id for manager in client.managers]  # assuming Client -> Manager relationship
    )).all()

    # Step 2: Delete candidate mappings for these jobs
    job_ids = [job.job_id for job in jobs]
    if job_ids:
        db.query(CandidateJDMapping).filter(CandidateJDMapping.jd_id.in_(job_ids)).delete(synchronize_session=False)

    # Step 3: Delete jobs
    if jobs:
        db.query(Job).filter(Job.job_id.in_(job_ids)).delete(synchronize_session=False)

    # Step 4: Delete client
    db.delete(client)

    db.commit()

    return JSONResponse(content={"message": f"Client '{client.client_name}' and related jobs deleted successfully!"})

# ------------------------------
# 4. Toggle Client Status
# ------------------------------
@router.post("/toggle/{client_id}")
def toggle_client_status_api(client_id: int, db: Session = Depends(get_db)):
    client = toggle_client_status(db, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

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

# View a single client and their jobs
@router.get("/{client_id}", name="client_detail_page")
def client_detail(request: Request, client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Load jobs for this client
    jobs = db.query(Job).filter(Job.client_id == client_id).order_by(Job.created_at.desc()).all()

    return templates.TemplateResponse(
        "client_jobs.html",
        {"request": request, "client": client, "jobs": jobs}
    )

# ------------------------------
# 6. Edit Client (without updated_by)
# ------------------------------
@router.post("/edit/{client_id}")
def edit_client(
    client_id: int,
    new_name: str = Form(...),
    db: Session = Depends(get_db)
):
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Check for duplicate client name
    existing_client = db.query(Client).filter(
        Client.client_name == new_name,
        Client.client_id != client_id
    ).first()
    if existing_client:
        raise HTTPException(status_code=400, detail=f"Client '{new_name}' already exists")

    # Update fields
    client.client_name = new_name
    client.updated_at = datetime.now(IST)   # keep track of last update time

    db.commit()
    db.refresh(client)

    return {"message": f"Client '{new_name}' updated successfully!"}
