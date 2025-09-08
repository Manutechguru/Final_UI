# landing_page_app/utils/clients_utils.py

from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from landing_page_app.models.clients import Client
from landing_page_app.models.jobs import Job
from landing_page_app.models.managers import Manager


# -----------------------------
# Fetch Client by ID
# -----------------------------
def get_client_by_id(db: Session, client_id: int) -> Optional[Client]:
    return db.query(Client).filter(Client.client_id == client_id).first()


# -----------------------------
# Fetch All Clients (Latest First)
# -----------------------------
def get_all_clients(db: Session) -> List[Client]:
    return db.query(Client).order_by(Client.created_at.desc()).all()


# -----------------------------
# Add New Client
# -----------------------------
def add_client(db: Session, client_name: str) -> Client:
    client = Client(client_name=client_name, status="active")
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


# -----------------------------
# Delete Client + Its Jobs
# -----------------------------
def delete_client(db: Session, client_id: int) -> bool:
    client = get_client_by_id(db, client_id)
    if not client:
        return False

    db.query(Job).filter(Job.client_id == client_id).delete(synchronize_session=False)
    db.delete(client)
    db.commit()
    return True



def toggle_client_status(db: Session, client_id: int) -> Optional[Client]:
    client = get_client_by_id(db, client_id)
    if not client:
        return None

    # Toggle client status
    client.status = "inactive" if client.status == "active" else "active"
    db.commit()
    db.refresh(client)

    # Cascade: make all managers & jobs match client status
    managers = db.query(Manager).filter(Manager.client_id == client_id).all()
    for manager in managers:
        manager.status = client.status
        db.commit()
        db.refresh(manager)

        jobs = db.query(Job).filter(Job.manager_id == manager.manager_id).all()
        for job in jobs:
            job.status = client.status
    db.commit()

    return client


# -----------------------------
# Get Client Statistics
# -----------------------------
def get_client_stats(db: Session) -> Dict[str, int]:
    return {
        "total_clients": db.query(Client).count(),
        "active_clients": db.query(Client).filter(Client.status == "active").count(),
        "inactive_clients": db.query(Client).filter(Client.status == "inactive").count(),
    }


# -----------------------------
# Get Jobs for a Client
# -----------------------------
def get_jobs_for_client(db: Session, client_id: int) -> List[Job]:
    return db.query(Job).filter(Job.client_id == client_id).order_by(Job.created_at.desc()).all()


# -----------------------------
# Check if Client Exists
# -----------------------------
def client_exists(db: Session, client_name: str) -> bool:
    return db.query(Client).filter(Client.client_name == client_name).first() is not None
