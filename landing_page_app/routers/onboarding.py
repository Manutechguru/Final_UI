from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, Body
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import os
from pathlib import Path



from landing_page_app.database import get_db
from landing_page_app.models.jobs import Job
from landing_page_app.models.managers import Manager
from landing_page_app.models.clients import Client
from landing_page_app.models.preboarding import (
    PreboardingCase,
    PreboardingStep,
    PreboardingDocument,
)
from landing_page_app.models.onboarding import (
    OnboardingCase,
    OnboardingStep,
    OnboardingDocument
)
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.models.preboarding import PreboardingDocument
from landing_page_app.models.user import User
from landing_page_app.routers.auth import get_current_user

from landing_page_app.routers.utils.onboarding_utils import (
    ONBOARDING_STEPS,
    compute_onboarding_status,
    validate_step_data,
    validate_status_transition,
    ensure_no_previous_failure,
)


router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


# ============================================================
# HELPERS
# ============================================================

def require_onboarding_stage(mapping: CandidateJDMapping):
    if mapping.stage != "Onboarding":
        raise HTTPException(
            status_code=400,
            detail="Candidate is not in Onboarding stage"
        )


def get_or_create_case(db, candidate_id: int, jd_id: int):
    case = (
        db.query(OnboardingCase)
        .filter(
            OnboardingCase.candidate_id == candidate_id,
            OnboardingCase.jd_id == jd_id
        )
        .first()
    )

    if case:
        return case

    case = OnboardingCase(
        candidate_id=candidate_id,
        jd_id=jd_id
    )
    db.add(case)
    db.flush()

    for step in ONBOARDING_STEPS:
        db.add(
            OnboardingStep(
                case_id=case.id,
                step_type=step
            )
        )

    db.commit()
    db.refresh(case)
    return case


def get_step_or_404(db, case_id: int, step_type: str):
    step = (
        db.query(OnboardingStep)
        .filter(
            OnboardingStep.case_id == case_id,
            OnboardingStep.step_type == step_type
        )
        .first()
    )

    if not step:
        raise HTTPException(404, "Onboarding step not found")

    return step


# ============================================================
# FETCH / INIT CASE
# ============================================================

@router.get("/case")
def fetch_onboarding_case(
    candidate_id: int,
    jd_id: int,
    db: Session = Depends(get_db)
):
    mapping = (
        db.query(CandidateJDMapping)
        .filter(
            CandidateJDMapping.candidate_id == candidate_id,
            CandidateJDMapping.jd_id == jd_id
        )
        .first()
    )

    if not mapping:
        raise HTTPException(404, "Candidate-JD mapping not found")

    require_onboarding_stage(mapping)

    case = get_or_create_case(db, candidate_id, jd_id)

    return {
        "case_id": case.id,
        "candidate_id": case.candidate_id,   # ✅ ADD THIS
        "jd_id": case.jd_id,
        "final_status": case.final_status,
        "steps": [
            {
                "step_type": s.step_type,
                "status": s.status,
                "data": s.data,
                "documents": [
                    {
                        "id": d.id,
                        "doc_type": d.doc_type,
                        "file_url": d.file_url,
                        "verified": d.verified
                    } for d in s.documents
                ]
            }
            for s in case.steps
        ]
    }


# ============================================================
# UPDATE STEP (FIELDS + STATUS)
# ============================================================

@router.post("/step/update")
async def update_onboarding_step(
    case_id: int,
    step_type: str,
    status: str,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    step = get_step_or_404(db, case_id, step_type)

    validate_status_transition(step, status)
    ensure_no_previous_failure(step.case.steps, step_type)

    if status == "CLEARED":
        validate_step_data(step_type, data)

    step.status = status
    step.data = data
    step.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True}


# ============================================================
# UPLOAD DOCUMENT (CHEQUE / PASSBOOK)
# ============================================================

@router.post("/document/upload")
async def upload_onboarding_document(
    case_id: int,
    step_type: str,
    doc_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    step = get_step_or_404(db, case_id, step_type)

    # ❌ BLOCK PAN / AADHAAR
    forbidden_docs = ["PAN", "AADHAAR"]
    if doc_type.upper() in forbidden_docs:
        raise HTTPException(400, "Identity documents must come from Preboarding")

    # ✅ CREATE DIRECTORY
    upload_dir = Path("uploads") / "onboarding" / str(case_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / file.filename
    file_url = f"/uploads/onboarding/{case_id}/{file.filename}"

    with open(file_path, "wb") as f:
        f.write(await file.read())

    # 🔁 🔥 THIS IS THE KEY FIX (REPLACE OLD DOC)
    db.query(OnboardingDocument).filter(
        OnboardingDocument.step_id == step.id,
        OnboardingDocument.doc_type == doc_type,
    ).update(
        {
            "is_active": False,
            "replaced_at": datetime.utcnow()
        }
    )

    # ✅ INSERT NEW DOCUMENT
    doc = OnboardingDocument(
        step_id=step.id,
        doc_type=doc_type,
        file_url=file_url,
        verified="PENDING",
        is_active=True
    )

    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "file_url": doc.file_url
    }


# ============================================================
# FINALIZE ONBOARDING
# ============================================================

@router.post("/complete")
def complete_onboarding(
    candidate_id: int,
    jd_id: int,
    confirm_joining: bool,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    mapping = (
        db.query(CandidateJDMapping)
        .filter(
            CandidateJDMapping.candidate_id == candidate_id,
            CandidateJDMapping.jd_id == jd_id
        )
        .first()
    )

    if not mapping:
        raise HTTPException(404, "Mapping not found")

    require_onboarding_stage(mapping)

    case = (
        db.query(OnboardingCase)
        .filter(
            OnboardingCase.candidate_id == candidate_id,
            OnboardingCase.jd_id == jd_id
        )
        .first()
    )

    if not case:
        raise HTTPException(404, "Onboarding case not found")

    final_status = compute_onboarding_status(case.steps)

    if not confirm_joining:
        final_status = "FAILED"

    case.final_status = final_status
    db.commit()

    # 🔁 AUTO STAGE TRANSITION
    if final_status == "COMPLETED":
        mapping.stage = "Hired"
    elif final_status == "FAILED":
        mapping.stage = "Rejected"

    db.commit()

    return {
        "final_status": final_status,
        "candidate_stage": mapping.stage
    }


# ============================================================
# ADMIN OVERRIDE (RESET STEP / FORCE STATUS)
# ============================================================

@router.post("/admin/override")
def admin_override(
    case_id: int,
    step_type: str,
    new_status: str,
    reason: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):

    if user.role.lower() != "admin":
        raise HTTPException(403, "Admin access required")

    step = get_step_or_404(db, case_id, step_type)

    step.status = new_status
    step.updated_at = datetime.utcnow()

    db.commit()

    # ⚠️ YOU ALREADY LOG THIS PATTERN IN PREBOARDING
    # Reuse same logging mechanism (DO NOT DUPLICATE)

    return {"success": True}


@router.get("/joining-details/meta")
def get_joining_details_meta(
    jd_id: int,
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.job_id == jd_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    manager = db.query(Manager).filter(
        Manager.manager_id == job.manager_id,
        Manager.status == "active"
    ).first()

    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")

    client = db.query(Client).filter(
        Client.client_id == manager.client_id,
        Client.status == "active"
    ).first()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return {
        "client": {
            "id": client.client_id,
            "name": client.client_name,
        },
        "manager": {
            "id": manager.manager_id,
            "name": manager.manager_name,
        }
    }

@router.get("/payroll/pan")
def fetch_pan_from_preboarding(
    candidate_id: int,
    jd_id: int,
    db: Session = Depends(get_db),
):
    # 1️⃣ Fetch preboarding case
    case = db.query(PreboardingCase).filter(
        PreboardingCase.candidate_id == candidate_id,
        PreboardingCase.jd_id == jd_id
    ).first()

    if not case:
        raise HTTPException(404, "Preboarding case not found")

    # 2️⃣ Fetch PAN via STEP → DOCUMENT (CORRECT RELATION)
    pan_doc = (
        db.query(PreboardingDocument)
        .join(
            PreboardingStep,
            PreboardingDocument.step_id == PreboardingStep.id
        )
        .filter(
            PreboardingStep.case_id == case.id,
            PreboardingDocument.doc_type.in_(["PAN", "PAN_CARD"])
        )
        .order_by(PreboardingDocument.uploaded_at.desc())
        .first()
    )

    if not pan_doc:
        raise HTTPException(404, "PAN not available")

    return {
        "file_url": pan_doc.file_url,
        "verified": pan_doc.verified
    }


@router.get("/documents")
def get_onboarding_document(
    case_id: int,
    doc_type: str,
    db: Session = Depends(get_db)
):
    # 1️⃣ Find PAYROLL step for this case
    payroll_step = (
        db.query(OnboardingStep)
        .filter(
            OnboardingStep.case_id == case_id,
            OnboardingStep.step_type == "PAYROLL"
        )
        .first()
    )

    if not payroll_step:
        raise HTTPException(
            status_code=404,
            detail="PAYROLL step not found for case"
        )

    # 2️⃣ Find document linked to that step
    document = (
        db.query(OnboardingDocument)
        .filter(
            OnboardingDocument.step_id == payroll_step.id,
            OnboardingDocument.doc_type == doc_type
        )
        .first()
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    return {
        "file_url": document.file_url,
        "verified": document.verified,
    }
