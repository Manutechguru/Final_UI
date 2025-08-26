from fastapi import APIRouter, Body, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from landing_page_app.database import get_db
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.jobs import Job

router = APIRouter(prefix="/candidates", tags=["Candidate Shortlisting"])

# ----------------------------------------------------------------------
# SHORTLIST CANDIDATES
# ----------------------------------------------------------------------
@router.post("/{job_id}/shortlist")
def shortlist_candidates(
    job_id: int,
    candidate_ids: List[int] = Body(...),
    db: Session = Depends(get_db)
):
    """Mark selected candidates as Shortlisted for a job."""

    # ✅ Check if job exists
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not candidate_ids:
        raise HTTPException(status_code=400, detail="No candidates provided.")

    updated = 0
    added = 0

    for cid in candidate_ids:
        mapping = (
            db.query(CandidateJDMapping)
            .filter(
                CandidateJDMapping.jd_id == job_id,
                CandidateJDMapping.candidate_id == cid
            )
            .first()
        )

        if mapping:
            # ✅ Update stage & status if already mapped
            mapping.stage = "Shortlisted"
            mapping.status = "Screening"
            mapping.updated_at = datetime.utcnow()
            updated += 1
        else:
            # ✅ Add new mapping if not exists
            db.add(
                CandidateJDMapping(
                    jd_id=job_id,
                    candidate_id=cid,
                    stage="Shortlisted",
                    status="Screening",
                    updated_at=datetime.utcnow(),
                )
            )
            added += 1

    db.commit()
    return JSONResponse(
        content={
            "message": f"{updated} candidates updated, {added} candidates added.",
            "total": updated + added
        }
    )

# ----------------------------------------------------------------------
# REJECT CANDIDATES
# ----------------------------------------------------------------------
@router.post("/{job_id}/reject")
def reject_candidates(
    job_id: int,
    candidate_ids: List[int] = Body(...),
    db: Session = Depends(get_db)
):
    """Mark selected candidates as Rejected for a job."""

    # ✅ Check if job exists
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not candidate_ids:
        raise HTTPException(status_code=400, detail="No candidates provided.")

    updated = 0
    added = 0

    for cid in candidate_ids:
        mapping = (
            db.query(CandidateJDMapping)
            .filter(
                CandidateJDMapping.jd_id == job_id,
                CandidateJDMapping.candidate_id == cid
            )
            .first()
        )

        if mapping:
            mapping.stage = "Rejected"
            mapping.status = "Rejected"
            mapping.updated_at = datetime.utcnow()
            updated += 1
        else:
            db.add(
                CandidateJDMapping(
                    jd_id=job_id,
                    candidate_id=cid,
                    stage="Rejected",
                    status="Rejected",
                    updated_at=datetime.utcnow(),
                )
            )
            added += 1

    db.commit()
    return JSONResponse(
        content={
            "message": f"{updated} candidates updated, {added} candidates added.",
            "total": updated + added
        }
    )
