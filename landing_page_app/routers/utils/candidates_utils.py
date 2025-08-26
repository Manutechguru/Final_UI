# landing_page_app/utils/candidates_utils.py

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Dict, Optional
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping
import re

# -----------------------------
# Fetch Candidate by ID
# -----------------------------
def get_candidate_by_id(db: Session, candidate_id: int) -> Optional[Candidate]:
    return db.query(Candidate).filter(Candidate.candidates_id == candidate_id).first()


# -----------------------------
# Fetch Multiple Candidates by IDs
# -----------------------------
def get_candidates_by_ids(db: Session, candidate_ids: List[int]) -> List[Candidate]:
    return db.query(Candidate).filter(Candidate.candidates_id.in_(candidate_ids)).all()


# -----------------------------
# Search Candidates (Basic)
# -----------------------------
def search_candidates(db: Session, search_query: str) -> List[Candidate]:
    """
    Basic search based on name, email, skillset, or company.
    """
    return db.query(Candidate).filter(
        or_(
            Candidate.candidate_name.ilike(f"%{search_query}%"),
            Candidate.email.ilike(f"%{search_query}%"),
            Candidate.skillset.ilike(f"%{search_query}%"),
            Candidate.company.ilike(f"%{search_query}%")
        )
    ).all()



# -----------------------------
# Get Candidate's Latest Status for a Job
# -----------------------------
def get_latest_candidate_status(db: Session, candidate_id: int, jd_id: int) -> str:
    """
    Fetch the latest status for a candidate under a specific JD.
    """
    mapping = (
        db.query(CandidateJDMapping)
        .filter(
            CandidateJDMapping.candidate_id == candidate_id,
            CandidateJDMapping.jd_id == jd_id
        )
        .order_by(CandidateJDMapping.updated_at.desc())
        .first()
    )
    return mapping.stage if mapping else "Not Updated"


# -----------------------------
# Get Candidates Linked to a Job
# -----------------------------
def get_candidates_for_job(db: Session, jd_id: int) -> List[Dict]:
    """
    Fetch all candidates linked to a specific JD with their latest status.
    """
    candidates = (
        db.query(Candidate)
        .join(CandidateJDMapping, Candidate.candidates_id == CandidateJDMapping.candidate_id)
        .filter(CandidateJDMapping.jd_id == jd_id)
        .all()
    )

    result = []
    for c in candidates:
        latest_status = get_latest_candidate_status(db, c.candidates_id, jd_id)
        result.append({
            "candidates_id": c.candidates_id,
            "candidate_name": c.candidate_name,
            "email": c.email,
            "contact": c.contact,
            "location": c.location,
            "skillset": c.skillset,
            "status": latest_status
        })
    return result

