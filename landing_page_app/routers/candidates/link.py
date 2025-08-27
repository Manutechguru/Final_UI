from fastapi import APIRouter, Body, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List

from landing_page_app.database import get_db
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.models.jobs import Job

from landing_page_app.routers.utils.link_utils import (
    link_candidates_to_jd_db,
    fetch_jd_candidates
)
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="landing_page_app/templates")
router = APIRouter(prefix="/candidates", tags=["Candidates Linking"])

# ----------------------------------------------------------------------
# LINK SELECTED CANDIDATES TO A JD
# ----------------------------------------------------------------------
@router.post("/link-to-jd")
def link_to_jd(
    jd_id: int = Body(...),
    candidate_ids: List[int] = Body(...),
    db: Session = Depends(get_db)
):
    if not candidate_ids:
        raise HTTPException(status_code=400, detail="No candidates selected.")
    
    linked_count = link_candidates_to_jd_db(db, jd_id, candidate_ids)
    
    return JSONResponse({"message": f"Linked {linked_count} candidates successfully."})


# ----------------------------------------------------------------------
# JD CANDIDATES PAGE
# ----------------------------------------------------------------------
@router.get("/jd-candidates/{jd_id}")
def jd_candidates_page(jd_id: int, request: Request, db: Session = Depends(get_db)):
    candidates = fetch_jd_candidates(db, jd_id)
    return templates.TemplateResponse(
        "jd_candidates.html",
        {
            "request": request,
            "jd_id": jd_id,
            "candidates": candidates,
            "status_options": ["Screening", "Submissions", "Interview",
                               "Offered", "Hired", "Rejected", "Archived"]
        }
    )


# ----------------------------------------------------------------------
# UPDATE STAGE OF CANDIDATE
# ----------------------------------------------------------------------
@router.post("/update-stage")
def update_candidate_stage(
    jd_id: int = Body(...),
    candidate_id: int = Body(...),
    stage: str = Body(...),
    db: Session = Depends(get_db)
):
    mapping = db.query(CandidateJDMapping).filter(
        CandidateJDMapping.jd_id == jd_id,
        CandidateJDMapping.candidate_id == candidate_id
    ).first()
    
    if not mapping:
        raise HTTPException(status_code=404, detail="Candidate mapping not found.")
    
    mapping.stage = stage
    db.commit()
    return JSONResponse({"message": f"Updated stage to {stage}"})
  
  