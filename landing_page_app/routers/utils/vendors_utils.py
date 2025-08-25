# landing_page_app/routers/utils/vendors_utils.py
from sqlalchemy.orm import Session
from typing import List, Optional
from landing_page_app.models.clients import Client
from landing_page_app.models.managers import Manager
from landing_page_app.models.jobs import Job
from datetime import datetime

# -----------------------------
# Get manager by ID
# -----------------------------
def get_manager_by_id(db: Session, manager_id: int) -> Optional[Manager]:
    return db.query(Manager).filter(Manager.manager_id == manager_id).first()

# -----------------------------
# Get all managers under a client
# -----------------------------
def get_managers_for_client(db: Session, client_id: int) -> List[Manager]:
    return db.query(Manager).filter(Manager.client_id == client_id).order_by(Manager.created_at.desc()).all()

# -----------------------------
# Add new manager under a client
# -----------------------------
def add_manager(db: Session, client_id: int, manager_name: str) -> Manager:
    # Default status to active
    manager = Manager(
        client_id=client_id,
        manager_name=manager_name,
        status="active",
        created_at=datetime.utcnow()
    )
    db.add(manager)
    db.commit()
    db.refresh(manager)
    return manager

# -----------------------------
# Delete manager (and jobs under manager)
# -----------------------------
def delete_manager(db: Session, manager_id: int) -> bool:
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        return False
    # Delete all jobs under this manager
    db.query(Job).filter(Job.manager_id == manager_id).delete(synchronize_session=False)
    db.delete(manager)
    db.commit()
    return True

# -----------------------------
# Toggle manager status (active/inactive)
# -----------------------------
def toggle_manager_status(db: Session, manager_id: int) -> Optional[Manager]:
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        return None
    manager.status = "inactive" if manager.status == "active" else "active"
    db.commit()
    db.refresh(manager)
    return manager

# -----------------------------
# Check if a manager already exists under a client
# -----------------------------
def manager_exists(db: Session, client_id: int, manager_name: str) -> bool:
    existing_manager = db.query(Manager).filter(
        Manager.client_id == client_id,
        Manager.manager_name == manager_name
    ).first()
    return existing_manager is not None
