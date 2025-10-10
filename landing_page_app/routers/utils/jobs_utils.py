from sqlalchemy.orm import Session
from datetime import datetime
from landing_page_app.models.managers import Manager
from landing_page_app.models.jobs import Job
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.models.user import User
from zoneinfo import ZoneInfo
import logging

# Define IST timezone once
IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)

# -----------------------------
# Get Manager by ID
# -----------------------------
def get_manager_by_id(db: Session, manager_id: int) -> Manager | None:
    try:
        manager = db.query(Manager).filter(Manager.manager_id == manager_id).first()
        return manager
    except Exception as e:
        logger.error(f"Error getting manager by ID {manager_id}: {str(e)}")
        return None


# -----------------------------
# Get Jobs by Manager
# -----------------------------
def get_jobs_by_manager(db: Session, manager_id: int) -> list[Job]:
    try:
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

        logger.info(f"Retrieved {len(jobs)} jobs for manager {manager_id}")
        return jobs
    except Exception as e:
        logger.error(f"Error getting jobs for manager {manager_id}: {str(e)}")
        return []


# -----------------------------
# Add New Job for Manager
# -----------------------------
def add_new_job(db: Session, manager_id: int, job_title: str, job_description: str = "") -> Job:
    try:
        # Clean inputs
        job_title_clean = (job_title or "").strip()
        job_description_clean = (job_description or "").strip()
        
        if not job_title_clean:
            raise ValueError("Job title is required")

        # Check if job already exists for this manager
        existing_job = (
            db.query(Job)
            .filter(
                Job.manager_id == manager_id,
                Job.job_title.ilike(job_title_clean)
            )
            .first()
        )
        
        if existing_job:
            raise ValueError(f"Job '{job_title_clean}' already exists for this manager")

        job = Job(
            manager_id=manager_id,
            job_title=job_title_clean,
            job_description=job_description_clean,
            status="active",   # ✅ FIXED: Default new jobs to ACTIVE
            created_by=None,
            created_at=datetime.now(IST),
            updated_by=None,
            updated_at=None
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        logger.info(f"Successfully added job '{job_title_clean}' for manager {manager_id}")
        return job
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding new job for manager {manager_id}: {str(e)}")
        raise e



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
    try:
        job = (
            db.query(Job)
            .filter(Job.job_id == job_id, Job.manager_id == manager_id)
            .first()
        )
        if not job:
            logger.warning(f"Job {job_id} not found for manager {manager_id}")
            return None

        # If client asked for explicit status, set it; otherwise flip
        old_status = job.status
        if desired_status in ("active", "inactive"):
            job.status = desired_status
        else:
            job.status = "inactive" if job.status == "active" else "active"

        job.updated_by = updated_by
        job.updated_at = datetime.now(IST)

        db.commit()
        db.refresh(job)
        
        logger.info(f"Toggled job {job_id} status from '{old_status}' to '{job.status}'")
        return job
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error toggling job status for job {job_id}: {str(e)}")
        return None


# -----------------------------
# Update Job for Manager
# -----------------------------
def update_job(
    db: Session, 
    manager_id: int, 
    job_id: int, 
    job_title: str, 
    job_description: str = "", 
    updated_by: int = None
) -> Job | None:
    try:
        job = (
            db.query(Job)
            .filter(Job.job_id == job_id, Job.manager_id == manager_id)
            .first()
        )
        if not job:
            logger.warning(f"Job {job_id} not found for manager {manager_id}")
            return None

        # Clean inputs
        job_title_clean = (job_title or "").strip()
        job_description_clean = (job_description or "").strip()
        
        if not job_title_clean:
            raise ValueError("Job title is required")

        # Check if another job with same title exists (excluding current job)
        existing_job = (
            db.query(Job)
            .filter(
                Job.manager_id == manager_id,
                Job.job_title.ilike(job_title_clean),
                Job.job_id != job_id
            )
            .first()
        )
        
        if existing_job:
            raise ValueError(f"Job '{job_title_clean}' already exists for this manager")

        job.job_title = job_title_clean
        job.job_description = job_description_clean
        job.updated_by = updated_by
        job.updated_at = datetime.now(IST)

        db.commit()
        db.refresh(job)
        
        logger.info(f"Successfully updated job {job_id} for manager {manager_id}")
        return job
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating job {job_id}: {str(e)}")
        raise e


# -----------------------------
# Delete Job for Manager
# -----------------------------
def delete_job(db: Session, job_id: int, manager_id: int) -> bool:
    try:
        job = (
            db.query(Job)
            .filter(Job.job_id == job_id, Job.manager_id == manager_id)
            .first()
        )
        if not job:
            logger.warning(f"Job {job_id} not found for manager {manager_id}")
            return False

        db.delete(job)
        db.commit()
        
        logger.info(f"Successfully deleted job {job_id} for manager {manager_id}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting job {job_id}: {str(e)}")
        return False


# -----------------------------
# Get Candidates for a Job
# -----------------------------
def get_candidates_by_job(db: Session, job_id: int) -> list[dict]:
    try:
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

        logger.info(f"Retrieved {len(results)} candidates for job {job_id}")
        return results
        
    except Exception as e:
        logger.error(f"Error getting candidates for job {job_id}: {str(e)}")
        return []


# -----------------------------
# Get Job by ID with Manager Validation
# -----------------------------
def get_job_by_id(db: Session, job_id: int, manager_id: int = None) -> Job | None:
    try:
        query = db.query(Job).filter(Job.job_id == job_id)
        if manager_id is not None:
            query = query.filter(Job.manager_id == manager_id)
        
        job = query.first()
        return job
    except Exception as e:
        logger.error(f"Error getting job by ID {job_id}: {str(e)}")
        return None


# -----------------------------
# Check if Job Exists for Manager
# -----------------------------
def job_exists(db: Session, manager_id: int, job_title: str) -> bool:
    try:
        job_title_clean = (job_title or "").strip().lower()
        existing_job = (
            db.query(Job)
            .filter(
                Job.manager_id == manager_id,
                Job.job_title.ilike(job_title_clean)
            )
            .first()
        )
        return existing_job is not None
    except Exception as e:
        logger.error(f"Error checking if job exists for manager {manager_id}: {str(e)}")
        return False


# -----------------------------
# Get All Active Jobs for Manager
# -----------------------------
def get_active_jobs_by_manager(db: Session, manager_id: int) -> list[Job]:
    try:
        jobs = (
            db.query(Job)
            .filter(
                Job.manager_id == manager_id,
                Job.status == "active"
            )
            .order_by(Job.created_at.desc())
            .all()
        )
        return jobs
    except Exception as e:
        logger.error(f"Error getting active jobs for manager {manager_id}: {str(e)}")
        return []


# -----------------------------
# Toggle Job Status (Individual Job - for frontend toggles)
# -----------------------------
def toggle_job_status_single(db: Session, job_id: int, user_id: int = None, desired_status: str = None):
    """
    Toggle job status between active and inactive - for individual job toggles
    """
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            return None
        
        # If desired_status is provided, use it; otherwise toggle
        if desired_status:
            new_status = desired_status.lower()
        else:
            new_status = 'inactive' if job.status == 'active' else 'active'
        
        # Validate status
        if new_status not in ('active', 'inactive'):
            return None
        
        old_status = job.status
        job.status = new_status
        if user_id:
            job.updated_by = user_id
        job.updated_at = datetime.now(IST)
        
        db.add(job)
        db.commit()
        db.refresh(job)
        
        logger.info(f"Toggled job {job_id} status from '{old_status}' to '{job.status}'")
        
        return {
            "job_id": job.job_id,
            "job_title": job.job_title,
            "new_status": job.status,
            "message": f"Job '{job.job_title}' is now {job.status}"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error toggling job status for job {job_id}: {str(e)}")
        return None


# -----------------------------
# Get Jobs by Manager with Status Filter
# -----------------------------
def get_jobs_by_manager_with_status(db: Session, manager_id: int, status: str = None):
    """
    Get jobs for a manager with optional status filter
    """
    try:
        query = db.query(Job).filter(Job.manager_id == manager_id)
        
        if status and status != 'all':
            query = query.filter(Job.status == status)
        
        jobs = query.order_by(Job.created_at.desc()).all()
        logger.info(f"Retrieved {len(jobs)} jobs for manager {manager_id} with status filter: {status}")
        return jobs
    except Exception as e:
        logger.error(f"Error getting filtered jobs for manager {manager_id}: {str(e)}")
        return []


# -----------------------------
# Delete Job (Individual - for frontend deletes)
# -----------------------------
def delete_job_single(db: Session, job_id: int):
    """
    Delete a job - for individual job deletion
    """
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            return False
        
        job_title = job.job_title
        db.delete(job)
        db.commit()
        
        logger.info(f"Successfully deleted job {job_id} - '{job_title}'")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting job {job_id}: {str(e)}")
        return False