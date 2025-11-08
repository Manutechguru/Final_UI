# landing_page_app/routers/candidates/link.py
from fastapi import APIRouter, Body, HTTPException, Depends, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from fastapi import Query
from fastapi.responses import RedirectResponse

from landing_page_app.database import get_db
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.routers.utils.link_utils import (
    link_candidates_to_jd_db,
    fetch_jd_candidates,
    remove_candidates_from_jd_db,
    update_recruiter_notes,
    update_candidate_ctc,
    update_candidate_notice_period
)

# Import templates
from landing_page_app.config import templates

# NEW imports for user
from landing_page_app.models.user import User
from landing_page_app.deps import get_current_user

router = APIRouter(prefix="/candidates", tags=["Candidates Linking"])

STATUS_OPTIONS = ["Screening", "Submissions", "Interview",
                  "Offered", "Hired", "Rejected", "Archived"]

# -----------------------------
# LINK SELECTED CANDIDATES TO A JD
# -----------------------------
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

# -----------------------------
# REMOVE SELECTED CANDIDATES FROM JD
# -----------------------------
@router.post("/remove-from-jd")
def remove_from_jd(
    jd_id: int = Body(...),
    candidate_ids: List[int] = Body(...),
    db: Session = Depends(get_db)
):
    if not candidate_ids:
        raise HTTPException(status_code=400, detail="No candidates selected to remove.")
    
    removed_count = remove_candidates_from_jd_db(db, jd_id, candidate_ids)
    return JSONResponse({"message": f"Removed {removed_count} candidates from shortlist successfully."})

# -----------------------------
# JD CANDIDATES PAGE WITH STAGE FILTER
# -----------------------------
@router.get("/jd-candidates/{jd_id}", response_class=HTMLResponse)
def jd_candidates_page(
    jd_id: int,
    request: Request,
    stage: Optional[str] = Query(None, description="Filter candidates by stage"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),  # <-- added
):
    """
    Render JD candidates page. If `stage` is provided, filter candidates by that stage.
    """
    candidates = fetch_jd_candidates(db, jd_id)
    
    from landing_page_app.models import Job
    job = db.query(Job).filter(Job.job_id == jd_id).first()
    job_title = job.job_title if job else "Candidates List"

    # Filter by stage if provided
    if stage and stage in STATUS_OPTIONS:
        candidates = [c for c in candidates if c.get("stage") == stage]

    return templates.TemplateResponse(
        "jd_candidates.html",
        {
            "request": request,
            "jd_id": jd_id,
            "candidates": candidates,
            "status_options": STATUS_OPTIONS,
            "selected_stage": stage or "All",
            "user": user,
            "job_title": job_title,# <-- added so header/profile works here
        }
    )

@router.get("/shortlist")
def shortlist_redirect(
    candidate_id: int = Query(..., description="Candidate ID to highlight"),
    job_id: Optional[int] = Query(None, description="Job / JD ID"),
    client_id: Optional[int] = Query(None, description="Client ID"),
    manager_id: Optional[int] = Query(None, description="Manager ID"),
):
    """
    Accepts query params and redirects to the JD candidates page (or constructs
    a URL your frontend expects). Keeps things backward-compatible with the
    existing frontend call to /candidates/shortlist?...
    """
    # If job_id is present, redirect to jd-candidates page and pass highlight param
    if job_id:
        # highlight param is used by the candidates page to highlight/scroll to candidate
        target = f"/candidates/jd-candidates/{job_id}?highlight={candidate_id}"
        # preserve client/manager if you need them in the querystring
        if client_id:
            target += f"&client_id={client_id}"
        if manager_id:
            target += f"&manager_id={manager_id}"
        return RedirectResponse(target)
    
    # fallback: if no job_id, redirect to candidate detail path (or show candidate page)
    # This avoids sending "shortlist" into the dynamic int route.
    return RedirectResponse(f"/candidates/{candidate_id}")


# -----------------------------
# UPDATE STAGE OF CANDIDATE
# -----------------------------
@router.put("/{candidate_id}/stage")
def update_candidate_stage(
    candidate_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)  # ✅ to identify who changed stage
):
    from landing_page_app.models.log import UserLog
    from landing_page_app.models.candidates import Candidate
    from landing_page_app.models.jobs import Job  # <-- if job model is named Job

    stage = payload.get("stage")
    jd_id = payload.get("jd_id")

    if not stage or not jd_id:
        raise HTTPException(status_code=400, detail="Stage and JD ID required")

    # find candidate mapping
    mapping = db.query(CandidateJDMapping).filter(
        CandidateJDMapping.jd_id == jd_id,
        CandidateJDMapping.candidate_id == candidate_id
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Candidate mapping not found.")

    old_stage = mapping.stage
    mapping.stage = stage
    mapping.updated_at = datetime.utcnow()

    # ✅ fetch candidate and job names for log message
    candidate = db.query(Candidate).filter(Candidate.candidates_id == candidate_id).first()
    job = db.query(Job).filter(Job.job_id == jd_id).first()

    candidate_name = candidate.candidate_name if candidate else f"ID {candidate_id}"
    job_title = job.job_title if job else f"JD ID {jd_id}"

    # ✅ build log text same as other entries
    log_text = (
        f"{user.full_name} changed stage of candidate {candidate_name} "
        f"from {old_stage or 'N/A'} to {stage} under job {job_title}"
    )

    db.add(UserLog(user_id=user.id, action=log_text))

    db.commit()
    return JSONResponse({"message": f"Updated stage to {stage}"})


# -----------------------------
# UPDATE RECRUITER NOTES
# -----------------------------
@router.post("/update-recruiter-notes")
def update_recruiter_notes_endpoint(
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update recruiter notes for a candidate.
    """
    candidate_id = payload.get("candidate_id")
    notes = payload.get("notes", "")
    
    if not candidate_id:
        raise HTTPException(status_code=400, detail="Candidate ID is required")
    
    success = update_recruiter_notes(db, candidate_id, notes)
    
    if success:
        return JSONResponse({"message": "Notes updated successfully"})
    else:
        raise HTTPException(status_code=404, detail="Candidate not found")

# -----------------------------
# UPDATE CTC
# -----------------------------
@router.post("/update-ctc")
def update_candidate_ctc_endpoint(
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    candidate_id = payload.get("candidate_id")
    ctc = payload.get("ctc")
    
    if not candidate_id or ctc is None:
        raise HTTPException(status_code=400, detail="Candidate ID and CTC are required")
    
    success = update_candidate_ctc(db, candidate_id, ctc)
    
    if success:
        return JSONResponse({"message": "CTC updated successfully"})
    else:
        raise HTTPException(status_code=404, detail="Candidate not found")

# -----------------------------
# UPDATE NOTICE PERIOD
# -----------------------------
@router.post("/update-notice-period")
def update_candidate_notice_period_endpoint(
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    candidate_id = payload.get("candidate_id")
    notice_period = payload.get("notice_period")
    
    if not candidate_id or notice_period is None:
        raise HTTPException(status_code=400, detail="Candidate ID and notice period are required")
    
    success = update_candidate_notice_period(db, candidate_id, notice_period)
    
    if success:
        return JSONResponse({"message": "Notice period updated successfully"})
    else:
        raise HTTPException(status_code=404, detail="Candidate not found")

# -----------------------------
# FETCH SINGLE CANDIDATE (for Edit)
# -----------------------------
@router.get("/{candidate_id}")
def get_candidate(candidate_id: int, db: Session = Depends(get_db)):
    candidate = db.query(Candidate).filter(Candidate.candidates_id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    return {
        "candidate": {
            "candidates_id": candidate.candidates_id,
            "candidate_name": candidate.candidate_name,
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
            "ctc": candidate.ctc,
            "recruitment_notes": candidate.recruitment_notes,
            "recruiter_notes": candidate.recruitment_notes,
            "ai_score": candidate.ai_score,
            "ai_explanation": candidate.ai_explanation,
        }
    }

# -----------------------------
# UPDATE CANDIDATE DETAILS (Edit)
# -----------------------------
@router.put("/{candidate_id}")
def update_candidate(candidate_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    candidate = db.query(Candidate).filter(Candidate.candidates_id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    for k, v in payload.items():
        if hasattr(candidate, k):
            setattr(candidate, k, v)
    db.commit()
    return {"message": "Candidate updated successfully"}
