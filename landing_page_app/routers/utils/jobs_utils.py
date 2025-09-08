from sqlalchemy.orm import Session
from datetime import datetime
from landing_page_app.models.managers import Manager
from landing_page_app.models.jobs import Job
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.models.user import User
from zoneinfo import ZoneInfo

# Define IST timezone once
IST = ZoneInfo("Asia/Kolkata")

# -----------------------------
# Get Manager by ID
# -----------------------------
def get_manager_by_id(db: Session, manager_id: int) -> Manager | None:
    manager = db.query(Manager).filter(Manager.manager_id == manager_id).first()
    return manager


# -----------------------------
# Get Jobs by Manager
# -----------------------------
def get_jobs_by_manager(db: Session, manager_id: int) -> list[Job]:
    jobs = (
        db.query(Job)
        .filter(Job.manager_id == manager_id)
        .order_by(Job.created_at.desc())
        .all()
    )

    # Ensure every job has a valid status
    updated = False
    for job in jobs:
        if not job.status:
            job.status = "inactive"
            updated = True
    if updated:
        db.commit()

    return jobs


# -----------------------------
# Add New Job for Manager
# -----------------------------
def add_new_job(db: Session, manager_id: int, job_title: str, job_description: str) -> Job:
    job = Job(
        manager_id=manager_id,
        job_title=job_title,
        job_description=job_description,
        status="inactive",
        created_by=None,
        created_at=datetime.now(IST),
        updated_by=None,
        updated_at=None
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


# -----------------------------
# Toggle Job Status for Manager
# -----------------------------
def toggle_job_status(
    db: Session,
    job_id: int,
    manager_id: int,
    desired_status: str = None,
    updated_by: int = None
) -> Job | None:
    job = (
        db.query(Job)
        .filter(Job.job_id == job_id, Job.manager_id == manager_id)
        .first()
    )
    if not job:
        return None

    # If client asked for explicit status, set it; otherwise flip
    if desired_status in ("active", "inactive"):
        job.status = desired_status
    else:
        job.status = "inactive" if job.status == "active" else "active"

    job.updated_by = updated_by
    job.updated_at = datetime.now(IST)

    db.commit()
    db.refresh(job)
    return job


# -----------------------------
# Update Job for Manager
# -----------------------------
def update_job(db: Session, manager_id: int, job_id: int, job_title: str, job_description: str, updated_by: int = None) -> Job | None:
    job = (
        db.query(Job)
        .filter(Job.job_id == job_id, Job.manager_id == manager_id)
        .first()
    )
    if not job:
        return None

    job.job_title = job_title
    job.job_description = job_description
    job.updated_by = updated_by
    job.updated_at = datetime.now(IST)

    db.commit()
    db.refresh(job)
    return job


# -----------------------------
# Delete Job for Manager
# -----------------------------
def delete_job(db: Session, job_id: int, manager_id: int) -> bool:
    job = (
        db.query(Job)
        .filter(Job.job_id == job_id, Job.manager_id == manager_id)
        .first()
    )
    if not job:
        return False

    db.delete(job)
    db.commit()
    return True


# -----------------------------
# Get Candidates for a Job
# -----------------------------
def get_candidates_by_job(db: Session, job_id: int) -> list[dict]:
    candidates = (
        db.query(
            Candidate.candidates_id,
            Candidate.candidate_name,
            CandidateJDMapping.stage,
            CandidateJDMapping.updated_at
        )
        .join(
            CandidateJDMapping,
            Candidate.candidates_id == CandidateJDMapping.candidate_id
        )
        .filter(CandidateJDMapping.jd_id == job_id)
        .order_by(CandidateJDMapping.updated_at.desc())
        .all()
    )

    results = []
    seen_candidates = set()

    for c_id, name, stage, updated_at in candidates:
        if c_id not in seen_candidates:
            results.append({
                "candidates_id": c_id,
                "candidate_name": name,
                "status": stage or "Not Updated",
                "updated_at": updated_at.strftime("%Y-%m-%d %H:%M") if updated_at else "N/A"
            })
            seen_candidates.add(c_id)

    return results
