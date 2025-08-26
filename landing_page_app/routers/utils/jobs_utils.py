from sqlalchemy.orm import Session
from datetime import datetime
from landing_page_app.models.managers import Manager
from landing_page_app.models.jobs import Job
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.models.user import User


# -----------------------------
# Get Manager by ID
# -----------------------------
def get_manager_by_id(db: Session, manager_id: int) -> Manager | None:
    return db.query(Manager).filter(Manager.manager_id == manager_id).first()


# -----------------------------
# Get all Jobs for a Manager
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
# Add a New Job under Manager
# -----------------------------
def add_new_job(
    db: Session,
    manager_id: int,
    job_title: str,
    job_description: str = "",
    status: str = "inactive",
    created_by: int = None
) -> Job:
    job_title_clean = job_title.strip()
    job_description_clean = job_description.strip() if job_description else ""

    new_job = Job(
        manager_id=manager_id,
        job_title=job_title_clean,
        job_description=job_description_clean,
        created_at=datetime.utcnow(),
        created_by=created_by,
        status=status
    )

    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job


# -----------------------------
# Get Job Details (With Creator & Updater Info)
# -----------------------------
def get_job_details(db: Session, job_id: int, manager_id: int):
    job = (
        db.query(Job)
        .filter(Job.job_id == job_id, Job.manager_id == manager_id)
        .first()
    )
    if not job:
        return None

    # Fetch creator & updater names
    creator = db.query(User.full_name).filter(User.id == job.created_by).scalar()
    updater = db.query(User.full_name).filter(User.id == job.updated_by).scalar()

    return {
        "job_id": job.job_id,
        "job_title": job.job_title,
        "job_description": job.job_description,
        "status": job.status,
        "created_by": creator or "N/A",
        "created_at": job.created_at.strftime("%Y-%m-%d %H:%M") if job.created_at else "N/A",
        "updated_by": updater or "N/A",
        "updated_at": job.updated_at.strftime("%Y-%m-%d %H:%M") if job.updated_at else "N/A"
    }


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

    if desired_status in ("active", "inactive"):
        job.status = desired_status
    else:
        job.status = "inactive" if job.status == "active" else "active"

    job.updated_by = updated_by
    job.updated_at = datetime.utcnow()

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
