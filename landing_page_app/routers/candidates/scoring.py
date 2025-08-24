from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from landing_page_app.database import get_db
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.jobs import Job
from landing_page_app.routers.utils.ai_utils import score_candidate  # Gemini scoring logic

router = APIRouter(prefix="/candidates", tags=["Candidate Scoring"])


# ----------------------------------------------------------------------
# SCORE A CANDIDATE AGAINST A JOB
# ----------------------------------------------------------------------
@router.post("/{candidate_id}/score/{jd_id}")
def score_candidate_for_job(
    candidate_id: int,
    jd_id: int,
    db: Session = Depends(get_db)
):
    """
    Score a candidate vs a JD using Gemini AI via ai_utils.score_candidate().
    If Gemini fails, fallback to a heuristic based on matching skillset + job title.
    """
    # Fetch candidate and job details
    candidate = db.query(Candidate).filter(Candidate.candidates_id == candidate_id).first()
    job = db.query(Job).filter(Job.job_id == jd_id).first()

    if not candidate or not job:
        raise HTTPException(status_code=404, detail="Candidate or JD not found")

    try:
        # Primary scoring via Gemini AI
        score = score_candidate(candidate, job)
    except Exception:
        # Fallback scoring if AI fails
        skillset = (candidate.skillset or "").lower()
        title = (job.job_title or "").lower()
        score = 80 if any(tok and tok in skillset for tok in title.split()) else 40

    return {
        "candidate_id": candidate_id,
        "jd_id": jd_id,
        "score": score
    }
