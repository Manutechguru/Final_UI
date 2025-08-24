from fastapi import APIRouter, Body, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from landing_page_app.database import get_db
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.models.clients import Client
from landing_page_app.models.jobs import Job

from landing_page_app.routers.utils.storage_utils import (
    save_candidate_metadata,
    save_candidate_resume
)

router = APIRouter(prefix="/candidates", tags=["Candidates Linking"])


# ----------------------------------------------------------------------
# LINK CANDIDATES TO JOB + SAVE RESUMES + METADATA
# ----------------------------------------------------------------------

@router.post("/link-to-job")
def link_candidates_to_job(
    client_id: int = Body(...),
    jd_id: int = Body(...),
    candidate_ids: List[int] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Link selected candidates to a job + save segregated resumes + metadata JSON.
    Folder structure:
        storage/
          └── <ClientName>_<ClientID>/
                └── <JobTitle>_<JobID>/
                      ├── resumes/
                      └── metadata/
    """
    if not candidate_ids:
        raise HTTPException(status_code=400, detail="No candidates selected.")

    # Fetch client + job details
    client = db.query(Client).filter(Client.client_id == client_id).first()
    job = db.query(Job).filter(Job.job_id == jd_id, Job.client_id == client_id).first()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found for this client.")

    linked_count = 0

    for c_id in candidate_ids:
        candidate = db.query(Candidate).filter(Candidate.candidates_id == c_id).first()
        if not candidate:
            continue

        # Save candidate resume in segregated folder
        if candidate.resumelinks:
            try:
                save_candidate_resume(
                    client.client_name, client.client_id,
                    job.job_title, job.job_id,
                    candidate.candidates_id,
                    candidate.resumelinks
                )
            except Exception as e:
                print(f"⚠️ Failed to save resume for candidate {c_id}: {e}")

        # Save candidate metadata JSON
        save_candidate_metadata(
            client.client_name, client.client_id,
            job.job_title, job.job_id,
            candidate.candidates_id,
            {
                "candidate_name": candidate.candidate_name,
                "email": candidate.email,
                "contact": candidate.contact,
                "location": candidate.location,
                "skillset": candidate.skillset,
                "education": candidate.education,
                "company": candidate.company,
                "resumelinks": candidate.resumelinks,
                "status": "Linked"
            }
        )

        # Update or create mapping in CandidateJDMapping
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
    return JSONResponse(
        content={"message": f"Linked {linked_count} candidates successfully."}
    )
