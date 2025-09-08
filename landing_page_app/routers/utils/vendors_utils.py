# landing_page_app/routers/utils/vendors_utils.py
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from landing_page_app.models.managers import Manager
from landing_page_app.models.jobs import Job
from landing_page_app.models.user import User
from sqlalchemy import func
from datetime import datetime
from zoneinfo import ZoneInfo   # ✅ Added for IST timezone

# Define IST timezone once
IST = ZoneInfo("Asia/Kolkata")

def get_manager_by_id(db: Session, manager_id: int) -> Optional[Manager]:
    return db.query(Manager).filter(Manager.manager_id == manager_id).first()

def get_managers_for_client(db: Session, client_id: int) -> List[Dict]:
    """
    Returns list of dicts with manager fields + created_by_name & updated_by_name
    (safe even if created_by/updated_by are NULL).
    """
    managers = db.query(Manager).filter(Manager.client_id == client_id).order_by(Manager.created_at.desc()).all()
    result = []
    for m in managers:
        created_user = None
        updated_user = None
        if getattr(m, "created_by", None) is not None:
            created_user = db.query(User).filter(User.id == m.created_by).first()
        if getattr(m, "updated_by", None) is not None:
            updated_user = db.query(User).filter(User.id == m.updated_by).first()

        result.append({
            "manager_id": m.manager_id,
            "manager_name": m.manager_name,
            "status": m.status,
            "created_at": m.created_at,
            "updated_at": m.updated_at,
            "created_by_name": created_user.full_name if created_user else "N/A",
            "updated_by_name": updated_user.full_name if updated_user else "N/A",
        })
    return result

def add_manager(db: Session, client_id: int, manager_name: str, user_id: Optional[int] = None) -> Dict:
    manager = Manager(
        client_id=client_id,
        manager_name=manager_name,
        status="active",
        created_at=datetime.now(IST),   # ✅ Changed to IST
        created_by=user_id,
        updated_at=datetime.now(IST),   # ✅ Changed to IST
        updated_by=user_id
    )
    db.add(manager)
    db.commit()
    db.refresh(manager)

    created_user = db.query(User).filter(User.id == user_id).first() if user_id else None
    return {
        "manager_id": manager.manager_id,
        "manager_name": manager.manager_name,
        "status": manager.status,
        "created_at": manager.created_at,
        "updated_at": manager.updated_at,
        "created_by_name": created_user.full_name if created_user else "N/A",
        "updated_by_name": created_user.full_name if created_user else "N/A",
    }

def delete_manager(db: Session, manager_id: int) -> bool:
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        return False
    # delete jobs under manager
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
    Returns dict with new_status & updated_by_name.
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

    # Audit trail
    manager.updated_by = user_id
    manager.updated_at = datetime.now(IST)
    db.commit()
    db.refresh(manager)

    # Cascade: Jobs follow manager status
    jobs = db.query(Job).filter(Job.manager_id == manager.manager_id).all()
    for job in jobs:
        job.status = manager.status
    db.commit()

    # Who updated
    updated_user = db.query(User).filter(User.id == user_id).first() if user_id else None

    return {
        "manager_id": manager.manager_id,
        "new_status": manager.status,
        "updated_by_name": updated_user.full_name if updated_user else "N/A",
        "updated_at": manager.updated_at.isoformat() if manager.updated_at else None
    }

def edit_manager(db: Session, manager_id: int, manager_name: str, user_id: Optional[int] = None) -> Optional[Dict]:
    manager = get_manager_by_id(db, manager_id)
    if not manager:
        return None
    manager.manager_name = manager_name
    manager.updated_by = user_id
    manager.updated_at = datetime.now(IST)   # ✅ Changed to IST
    db.commit()
    db.refresh(manager)

    updated_user = db.query(User).filter(User.id == user_id).first() if user_id else None
    return {
        "manager_id": manager.manager_id,
        "manager_name": manager.manager_name,
        "updated_by_name": updated_user.full_name if updated_user else "N/A",
        "updated_at": manager.updated_at.isoformat() if manager.updated_at else None
    }

def manager_exists(db: Session, client_id: int, manager_name: str) -> bool:
    return db.query(Manager).filter(
        Manager.client_id == client_id,
        func.lower(Manager.manager_name) == manager_name.strip().lower()
    ).first() is not None