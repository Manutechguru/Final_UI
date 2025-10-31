# landing_page_app/models/log.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func
from sqlalchemy.orm import Session
from landing_page_app.database import Base

class UserLog(Base):
    __tablename__ = "user_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    action = Column(String, nullable=False)  # e.g., LOGIN, SIGNUP, APPROVED
    timestamp = Column(DateTime(timezone=True), server_default=func.now())


# -----------------------
# Helper functions (explicit logging — Option B)
# -----------------------
def add_user_log(db: Session, user_id: int, action: str, commit: bool = False) -> None:
    """
    Add a single user log row.

    - db: SQLAlchemy Session (the same session used by the request)
    - user_id: integer id of the acting user (users.id)
    - action: short descriptive string. Keep it human-readable, e.g.:
        "CREATED JOB id:12 title:Backend Engineer"
        "EDITED CLIENT id:3 name:ACME Corp"
        "LINKED CANDIDATE id:5 to JOB id:12"
        "DEACTIVATED MANAGER id:8"
    - commit: if True, this function will call db.commit(). Default False so
              caller can group DB changes & commit once (preferred).
    """
    if not user_id or not action:
        # Silently ignore invalid log entries — don't raise to avoid breaking flows
        return
    try:
        
        if "LINKED CANDIDATE" in action or "UNLINKED CANDIDATE" in action:
            action = action.replace("id:", "ID:").replace(" to JOB ", " → JOB ")
            
        entry = UserLog(user_id=int(user_id), action=str(action))
        db.add(entry)
        if commit:
            db.commit()
    except Exception:
        # Fail-safe: do not propagate logging errors to user flows.
        try:
            db.rollback()
        except Exception:
            pass


def add_user_log_and_commit(db: Session, user_id: int, action: str) -> None:
    """
    Convenience wrapper that always commits immediately.
    Use this only when you want immediate persistence (rare).
    """
    add_user_log(db, user_id, action, commit=True)
