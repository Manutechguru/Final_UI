from fastapi import APIRouter, Body, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from landing_page_app.database import get_db
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.jobs import Job
from landing_page_app.models.clients import Client

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
    if not candidate_ids:
        raise HTTPException(status_code=400, detail="No candidates provided.")

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
            mapping.stage = "Shortlisted"
            mapping.updated_at = datetime.utcnow()
        else:
            db.add(
                CandidateJDMapping(
                    jd_id=job_id,
                    candidate_id=cid,
                    stage="Shortlisted",
                    updated_at=datetime.utcnow(),
                )
            )

    db.commit()
    return JSONResponse(
        content={"message": f"{len(candidate_ids)} candidates shortlisted successfully."}
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
    if not candidate_ids:
        raise HTTPException(status_code=400, detail="No candidates provided.")

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
            mapping.updated_at = datetime.utcnow()
        else:
            db.add(
                CandidateJDMapping(
                    jd_id=job_id,
                    candidate_id=cid,
                    stage="Rejected",
                    updated_at=datetime.utcnow(),
                )
            )

    db.commit()
    return JSONResponse(
        content={"message": f"{len(candidate_ids)} candidates rejected successfully."}
    )


# ----------------------------------------------------------------------
# MOVE CANDIDATE STAGE (Generic)
# ----------------------------------------------------------------------
@router.patch("/{candidate_id}/stage")
def update_candidate_stage(
    candidate_id: int,
    jd_id: int = Body(..., embed=True),
    stage: str = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """Update candidate stage for a specific JD (Generic stage updater)."""
    candidate = (
        db.query(Candidate)
        .filter(Candidate.candidates_id == candidate_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    mapping = (
        db.query(CandidateJDMapping)
        .filter(
            CandidateJDMapping.candidate_id == candidate_id,
            CandidateJDMapping.jd_id == jd_id
        )
        .first()
    )

    if mapping:
        mapping.stage = stage
        mapping.updated_at = datetime.utcnow()
    else:
        db.add(
            CandidateJDMapping(
                jd_id=jd_id,
                candidate_id=candidate_id,
                stage=stage,
                updated_at=datetime.utcnow()
            )
        )

    db.commit()
    return JSONResponse(
        content={
            "message": "Candidate stage updated successfully",
            "candidate_id": candidate_id,
            "jd_id": jd_id,
            "stage": stage,
        }
    )
