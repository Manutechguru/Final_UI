from sqlalchemy.orm import Session
from datetime import datetime
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping

# -----------------------------
# LINK CANDIDATES TO JD
# -----------------------------
def link_candidates_to_jd_db(db: Session, jd_id: int, candidate_ids: list):
    """
    Link selected candidates to a JD.
    If already linked, update stage to 'Linked'.
    """
    linked_count = 0
    existing_mappings = db.query(CandidateJDMapping).filter(
        CandidateJDMapping.jd_id == jd_id,
        CandidateJDMapping.candidate_id.in_(candidate_ids)
    ).all()
    existing_ids = {m.candidate_id for m in existing_mappings}

    for c_id in candidate_ids:
        if c_id in existing_ids:
            mapping = next(m for m in existing_mappings if m.candidate_id == c_id)
            mapping.stage = "Linked"
            mapping.updated_at = datetime.utcnow()
        else:
            db.add(CandidateJDMapping(
                jd_id=jd_id,
                candidate_id=c_id,
                stage="Linked",
                updated_at=datetime.utcnow()
            ))
        linked_count += 1

    db.commit()
    return linked_count

# -----------------------------
# REMOVE CANDIDATES FROM JD
# -----------------------------
def remove_candidates_from_jd_db(db: Session, jd_id: int, candidate_ids: list):
    """
    Remove selected candidates from a JD mapping.
    """
    removed_count = 0
    mappings = db.query(CandidateJDMapping).filter(
        CandidateJDMapping.jd_id == jd_id,
        CandidateJDMapping.candidate_id.in_(candidate_ids)
    ).all()

    for mapping in mappings:
        db.delete(mapping)
        removed_count += 1

    db.commit()
    return removed_count

# -----------------------------
# FETCH CANDIDATES LINKED TO A JD
# -----------------------------
def fetch_jd_candidates(db: Session, jd_id: int):
    """
    Fetch all candidates linked to a JD with their details.
    """
    rows = db.query(CandidateJDMapping, Candidate).join(
        Candidate, CandidateJDMapping.candidate_id == Candidate.candidates_id
    ).filter(
        CandidateJDMapping.jd_id == jd_id
    ).all()
    
    candidates = []
    for mapping, candidate in rows:
        candidates.append({
            "candidate_id": candidate.candidates_id,
            "candidate_name": candidate.candidate_name or "N/A",
            "email": candidate.email or "N/A",
            "skillset": candidate.skillset or "N/A",
            "it_experience": candidate.it_experience or "N/A",
            "location": candidate.location or "N/A",
            "contact": candidate.contact or "N/A",
            "relevant_experience": candidate.relevant_experience or "N/A",
            "education": candidate.education or "N/A",
            "company": candidate.company or "N/A",
            "resumelinks": candidate.resumelinks or None,
            "clients": getattr(candidate, "clients", "N/A"),
            "notice_period": candidate.notice_period or "N/A",
            "ctc": candidate.ctc or "N/A",
            "comment": candidate.comment or "N/A",
            "stage": mapping.stage or "Linked",
            "recruiter_notes": candidate.recruitment_notes or "",
            "ai_score": candidate.ai_score if candidate.ai_score is not None else "N/A",
            "ai_explanation": candidate.ai_explanation or "N/A",
        })
    return candidates

# -----------------------------
# UPDATE RECRUITER NOTES
# -----------------------------
def update_recruiter_notes(db: Session, candidate_id: int, notes: str):
    """
    Update recruiter notes for a candidate.
    """
    candidate = db.query(Candidate).filter(
        Candidate.candidates_id == candidate_id
    ).first()
    
    if not candidate:
        return False
    
    candidate.recruitment_notes = notes
    db.commit()
    return True

# -----------------------------
# UPDATE CTC
# -----------------------------
def update_candidate_ctc(db: Session, candidate_id: int, ctc):
    """
    Update CTC for a candidate. Accepts integer or float (e.g., 5 or 4.4).
    """
    candidate = db.query(Candidate).filter(
        Candidate.candidates_id == candidate_id
    ).first()
    
    if not candidate:
        return False
    
    candidate.ctc = ctc
    db.commit()
    return True

# -----------------------------
# UPDATE NOTICE PERIOD
# -----------------------------
def update_candidate_notice_period(db: Session, candidate_id: int, notice_period: str):
    """
    Update notice period for a candidate.
    """
    candidate = db.query(Candidate).filter(
        Candidate.candidates_id == candidate_id
    ).first()
    
    if not candidate:
        return False
    
    candidate.notice_period = notice_period
    db.commit()
    return True