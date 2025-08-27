from sqlalchemy.orm import Session
from datetime import datetime
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping

def link_candidates_to_jd_db(db: Session, jd_id: int, candidate_ids: list):
    linked_count = 0
    for c_id in candidate_ids:
        candidate = db.query(Candidate).filter(Candidate.candidates_id == c_id).first()
        if not candidate:
            continue

        mapping = db.query(CandidateJDMapping).filter(
            CandidateJDMapping.jd_id == jd_id,
            CandidateJDMapping.candidate_id == c_id
        ).first()

        if mapping:
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


def fetch_jd_candidates(db: Session, jd_id: int):
    rows = db.query(
        CandidateJDMapping,
        Candidate
    ).join(
        Candidate, CandidateJDMapping.candidate_id == Candidate.candidates_id
    ).filter(
        CandidateJDMapping.jd_id == jd_id
    ).all()
    
    candidates = []
    for mapping, candidate in rows:
        candidates.append({
            "candidate_id": candidate.candidates_id,
            "name": candidate.candidate_name or "N/A",
            "email": candidate.email or "N/A",
            "skills": candidate.skillset or "N/A",
            "it_experience": candidate.it_experience or "N/A",
            "location": candidate.location or "N/A",
            "contact": candidate.contact or "N/A",
            "relevant_experience": candidate.relevant_experience or "N/A",
            "education": candidate.education or "N/A",
            "company": candidate.company or "N/A",
            "resume": candidate.resumelinks or None,  # make sure HTML uses c.resume
            "clients": candidate.clients or "N/A",
            "notice_period": candidate.notice_period or "N/A",
            "comment": candidate.comment or "N/A",
            "stage": mapping.stage or mapping.status or "Applied",
            "ai_score": mapping.ai_score or "N/A"
        })
    return candidates