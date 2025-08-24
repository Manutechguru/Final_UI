from fastapi import APIRouter, Request, Form, HTTPException, Depends, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from landing_page_app.database import get_db
from landing_page_app.models.clients import Client
from landing_page_app.models.jobs import Job

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
                created_at=datetime.utcnow(),
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
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Delete related jobs
    db.query(Job).filter(Job.client_id == client_id).delete(synchronize_session=False)
    db.delete(client)
    db.commit()

    return JSONResponse(content={"message": f"Client '{client.client_name}' and related jobs deleted successfully!"})

# ------------------------------
# 4. Toggle Client Status
# ------------------------------
@router.post("/toggle/{client_id}")
def toggle_client_status(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client.status = "inactive" if client.status == "active" else "active"
    db.commit()
    db.refresh(client)

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
