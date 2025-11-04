# landing_page_app/routers/utils/vendors_utils.py
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from landing_page_app.models.managers import Manager
from landing_page_app.models.jobs import Job
from landing_page_app.models.user import User
from sqlalchemy import func
from datetime import datetime
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)

# Keep UTC as canonical time
UTC = ZoneInfo("Asia/Kolkata")


def get_manager_by_id(db: Session, manager_id: int) -> Optional[Manager]:
    return db.query(Manager).filter(Manager.manager_id == manager_id).first()


def get_managers_for_client(db: Session, client_id: int) -> List[Dict]:
    """
    Returns list of dicts with manager fields + created_by, created_by_name,
    updated_by, updated_by_name. Safe if created_by/updated_by are NULL.
    """
    managers = (
        db.query(Manager)
        .filter(Manager.client_id == client_id)
        .order_by(Manager.created_at.desc())
        .all()
    )

    result: List[Dict] = []
    for m in managers:
        created_by_id = getattr(m, "created_by", None)
        updated_by_id = getattr(m, "updated_by", None)

        created_user = None
        updated_user = None
        if created_by_id is not None:
            created_user = db.query(User).filter(User.id == created_by_id).first()
        if updated_by_id is not None:
            updated_user = db.query(User).filter(User.id == updated_by_id).first()

        result.append({
            "manager_id": m.manager_id,
            "manager_name": m.manager_name,
            "status": m.status,
            "created_at": m.created_at,
            "updated_at": m.updated_at,
            # Include numeric IDs so callers can detect NULL vs present
            "created_by": created_by_id,
            "updated_by": updated_by_id,
            # Friendly names (None if not present)
            "created_by_name": getattr(created_user, "full_name", None) if created_user else None,
            "updated_by_name": getattr(updated_user, "full_name", None) if updated_user else None,
        })

    return result


def add_manager(db: Session, client_id: int, manager_name: str, user_id: Optional[int] = None) -> Manager:
    """
    Create and return a Manager SQLAlchemy object with created_by set if provided.
    Returns the Manager object (preferred for callers).
    """
    # Log call for debugging if user_id missing
    if user_id is None:
        logger.info(f"add_manager called without user_id: client_id={client_id}, manager_name={manager_name!r}")

    manager = Manager(
        client_id=client_id,
        manager_name=(manager_name or "").strip(),
        status="active",
        created_at=datetime.utcnow(),
        created_by=user_id,
        updated_at=None,
        updated_by=None,
    )
    db.add(manager)
    db.commit()
    db.refresh(manager)

    return manager


def delete_manager(db: Session, manager_id: int) -> bool:
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        return False
    # delete jobs under manager (cascade may already do this; keep explicit delete)
    db.query(Job).filter(Job.manager_id == manager_id).delete(synchronize_session=False)
    db.delete(manager)
    db.commit()
    return True


def toggle_manager_status(
    db: Session,
    manager_id: int,
    user_id: Optional[int] = None,
    desired_status: Optional[str] = None
) -> Optional[Dict]:
    """
    Set explicit status if desired_status provided ('active' or 'inactive'),
    otherwise flip current status. Cascade: Jobs always follow manager status.
    Returns dict with new_status, updated_by (id), updated_by_name, updated_at.
    """
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        return None

    # Decide new status
    if isinstance(desired_status, str):
        desired = desired_status.strip().lower()
        if desired not in ("active", "inactive"):
            return None
        manager.status = desired
    else:
        manager.status = "inactive" if manager.status == "active" else "active"

    # Audit trail (use UTC)
    manager.updated_by = user_id
    manager.updated_at = datetime.utcnow()
    db.add(manager)
    db.commit()
    db.refresh(manager)

    # Cascade: Jobs follow manager status
    jobs = db.query(Job).filter(Job.manager_id == manager.manager_id).all()
    for job in jobs:
        job.status = manager.status
        db.add(job)
    db.commit()

    # Resolve updater name
    updated_user = db.query(User).filter(User.id == user_id).first() if user_id else None

    return {
        "manager_id": manager.manager_id,
        "new_status": manager.status,
        "updated_by": user_id,
        "updated_by_name": getattr(updated_user, "full_name", None) if updated_user else None,
        "updated_at": manager.updated_at.isoformat() if manager.updated_at else None
    }


def edit_manager(db: Session, manager_id: int, manager_name: str, user_id: Optional[int] = None) -> Optional[Dict]:
    """
    Edit manager name and set updated_by/updated_at. Returns a dict describing the update.
    """
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        return None

    manager.manager_name = (manager_name or "").strip()
    manager.updated_by = user_id
    manager.updated_at = datetime.utcnow()
    db.add(manager)
    db.commit()
    db.refresh(manager)

    updated_user = db.query(User).filter(User.id == user_id).first() if user_id else None

    return {
        "manager_id": manager.manager_id,
        "manager_name": manager.manager_name,
        "updated_by": manager.updated_by,
        "updated_by_name": getattr(updated_user, "full_name", None) if updated_user else None,
        "updated_at": manager.updated_at.isoformat() if manager.updated_at else None
    }


def manager_exists(db: Session, client_id: int, manager_name: str) -> bool:
    return db.query(Manager).filter(
        Manager.client_id == client_id,
        func.lower(Manager.manager_name) == manager_name.strip().lower()
    ).first() is not None
