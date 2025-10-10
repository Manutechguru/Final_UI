# landing_page_app/routes/pipeline_routes.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from landing_page_app.database import get_db
from landing_page_app.models import Client, Manager, Job, CandidateJDMapping, Candidate

router = APIRouter(tags=["Pipeline"])

# ----------------------------
# 1️⃣ Get all active clients
# ----------------------------
@router.get("/clients")
def get_clients(db: Session = Depends(get_db)):
    clients = (
        db.query(Client)
        .with_entities(Client.client_id, Client.client_name)
        .filter(Client.status == "active")
        .order_by(Client.client_name.asc())
        .all()
    )
    return [{"id": c.client_id, "name": c.client_name} for c in clients]


# ----------------------------
# 2️⃣ Get active managers by client_id
# ----------------------------
@router.get("/managers/{client_id}")
def get_managers(client_id: int, db: Session = Depends(get_db)):
    managers = (
        db.query(Manager)
        .with_entities(Manager.manager_id, Manager.manager_name)
        .filter(
            Manager.client_id == client_id,
            Manager.status == "active"
        )
        .order_by(Manager.manager_name.asc())
        .all()
    )

    if not managers:
        raise HTTPException(status_code=404, detail="No active managers found for this client")

    return [{"id": m.manager_id, "name": m.manager_name} for m in managers]


# ----------------------------
# 3️⃣ Get active jobs by manager_id
# ----------------------------
@router.get("/jobs/{manager_id}")
def get_jobs(manager_id: int, db: Session = Depends(get_db)):
    jobs = (
        db.query(Job)
        .with_entities(Job.job_id, Job.job_title)
        .filter(
            Job.manager_id == manager_id,
            Job.status == "active"
        )
        .order_by(Job.job_title.asc())
        .all()
    )

    if not jobs:
        raise HTTPException(status_code=404, detail="No active jobs found for this manager")

    return [{"id": j.job_id, "title": j.job_title} for j in jobs]


# ----------------------------
# 4️⃣ Get candidates by job_id (optional stage filter)
# ----------------------------
@router.get("/candidates/{job_id}")
def get_candidates(
    job_id: int,
    stage: str = Query(None, description="Optional stage filter (e.g., Screening, Interview)"),
    db: Session = Depends(get_db)
):
    # Join CandidateJDMapping with Candidate table
    query = (
        db.query(CandidateJDMapping, Candidate)
        .join(Candidate, CandidateJDMapping.candidate_id == Candidate.candidates_id)
        .filter(CandidateJDMapping.jd_id == job_id)
    )

    if stage:
        query = query.filter(CandidateJDMapping.stage.ilike(stage.strip()))

    results = query.order_by(CandidateJDMapping.updated_at.desc()).all()

    if not results:
        raise HTTPException(status_code=404, detail="No candidates found for this job")

    candidates = []
    for mapping, candidate in results:
        candidates.append({
            "id": candidate.candidates_id,
            "name": candidate.candidate_name,
            "contact": candidate.contact,
            "email": candidate.email,
            "location": candidate.location,
            "skillset": candidate.skillset,
            "relevant_experience": candidate.relevant_experience,
            "it_experience": candidate.it_experience,
            "education": candidate.education,
            "company": candidate.company,
            "resumelinks": candidate.resumelinks,
            "comment": candidate.comment,
            "clients": candidate.clients,
            "notice_period": candidate.notice_period,
            "recruitment_notes": candidate.recruitment_notes,
            "ai_score": mapping.ai_score if mapping.ai_score is not None else 0,
            "ai_explanation": candidate.ai_explanation,
            "stage": mapping.stage or "Unknown",
            "status": mapping.status or "Screening",
            "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None
        })

    return candidates
