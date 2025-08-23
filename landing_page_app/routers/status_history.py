from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from landing_page_app.database import get_db
from landing_page_app.models.candidate_status_history import CandidateJDMapping

router = APIRouter(prefix="/status", tags=["Status History"])

@router.get("/{candidate_id}")
def candidate_status_history(candidate_id: int, db: Session = Depends(get_db)):
    history = db.query(CandidateJDMapping).filter(CandidateJDMapping.candidate_id == candidate_id).order_by(CandidateJDMapping.updated_at.desc()).all()
    return [{"job_id": h.jd_id, "stage": h.stage, "updated_at": h.updated_at} for h in history]
