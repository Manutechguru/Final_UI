# landing_page_app/utils/clients_utils.py

from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from landing_page_app.models.clients import Client
from landing_page_app.models.jobs import Job
from landing_page_app.models.managers import Manager

# NEW: logging helper (non-invasive)
from landing_page_app.models.log import add_user_log


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
def add_client(db: Session, client_name: str, user_id: Optional[int] = None) -> Client:
    """
    Creates a client. Optional user_id may be provided to record who performed the action.
    Backwards compatible: callers that don't pass user_id still work.
    """
    client = Client(client_name=client_name, status="active")
    db.add(client)
    db.commit()
    db.refresh(client)

    # Log creation if actor provided
    if user_id:
        try:
            add_user_log(db, user_id, f"CREATED CLIENT id:{client.client_id} name:{client.client_name}")
        except Exception:
            # Fail-safe: don't break main flow if logging fails
            try:
                db.rollback()
            except Exception:
                pass

    return client


# -----------------------------
# Delete Client + Its Jobs
# -----------------------------
def delete_client(db: Session, client_id: int, user_id: Optional[int] = None) -> bool:
    """
    Deletes client and related jobs (behavior left unchanged).
    Optional user_id may be provided to record who performed the deletion.
    """
    client = get_client_by_id(db, client_id)
    if not client:
        return False

    # Capture name for logging before delete
    client_name_for_log = getattr(client, "client_name", None)

    db.query(Job).filter(Job.client_id == client_id).delete(synchronize_session=False)
    db.delete(client)
    db.commit()

    # Log deletion if actor provided
    if user_id:
        try:
            add_user_log(db, user_id, f"DELETED CLIENT id:{client_id} name:{client_name_for_log}")
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    return True


def toggle_client_status(db: Session, client_id: int, user_id: Optional[int] = None) -> Optional[Client]:
    """
    Toggle client status between 'active' and 'inactive', cascade to managers and jobs.
    Optional user_id may be provided to record who performed the toggle.
    """
    client = get_client_by_id(db, client_id)
    if not client:
        return None

    # Toggle client status
    client.status = "inactive" if client.status == "active" else "active"
    db.commit()
    db.refresh(client)

    # Log client status change
    if user_id:
        try:
            state = "ACTIVATED" if client.status == "active" else "DEACTIVATED"
            add_user_log(db, user_id, f"{state} CLIENT id:{client.client_id} name:{client.client_name}")
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    # Cascade: make all managers & jobs match client status
    managers = db.query(Manager).filter(Manager.client_id == client_id).all()
    for manager in managers:
        manager.status = client.status
        db.commit()
        db.refresh(manager)

        # Log manager status change
        if user_id:
            try:
                mstate = "ACTIVATED" if manager.status == "active" else "DEACTIVATED"
                add_user_log(db, user_id, f"{mstate} MANAGER id:{manager.manager_id} name:{getattr(manager, 'manager_name', None)}")
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass

        jobs = db.query(Job).filter(Job.manager_id == manager.manager_id).all()
        for job in jobs:
            job.status = client.status
            # Note: original flow commits after loop; preserving semantics
            # We still log per-job status update (best-effort; wrapped in try/except)
            if user_id:
                try:
                    jstate = "ACTIVATED" if job.status == "active" else "DEACTIVATED"
                    add_user_log(db, user_id, f"{jstate} JOB id:{getattr(job, 'job_id', None)} title:{getattr(job, 'job_title', None)}")
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass

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
