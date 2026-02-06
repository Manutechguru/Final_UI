# landing_page_app/routers/preboarding.py

from fastapi import APIRouter, Depends, HTTPException, Body, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from datetime import datetime
import uuid
import os

from landing_page_app.database import get_db
from landing_page_app.models import (
    PreboardingCase,
    PreboardingStep,
    PreboardingDocument,
    CandidateJDMapping,
    User,
)
from landing_page_app.deps import get_current_user
from landing_page_app.routers.utils.preboarding_utils import compute_final_status
from landing_page_app.models.log import UserLog

router = APIRouter(
    prefix="/preboarding",
    tags=["Preboarding"]
)


UPLOAD_DIR = "uploads/preboarding"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ------------------------------------------------------------------
# CONSTANTS (single source of truth)
# ------------------------------------------------------------------
PREBOARDING_STEPS = [
    "ID",
    "EDUCATION",
    "EXPERIENCE",
    "REFERENCE",
    "FINAL",
]

ALLOWED_STATUSES = {"CLEARED", "IN_PROGRESS", "FAILED"}

# REQUIRED DOCUMENTS PER STEP (STRICT)
REQUIRED_DOCS = {
    "ID": {
        "AADHAAR_OR_PASSPORT",
        "PAN_CARD",
        "ADDRESS_PROOF",
        "PASSPORT_PHOTO",
    },
    "EDUCATION": {
        "DEGREE_CERTIFICATE",
        "SEM_MARKSHEETS",
        "INTERMEDIATE_CERT",
        "SSC_CERT",
    },
    "EXPERIENCE": {
        "OFFER_LETTER",
        "RELIEVING_LETTER",
        "PAYSLIPS",
        "PF_UAN",
        "GAP_EXPLANATION",
    },
    "REFERENCE": {
        "REF_1",
        "REF_2",
        "REF_CONTACT",
    },
}

# ------------------------------------------------------------------
# 1️⃣ GET / CREATE PREBOARDING CASE (ENTRY POINT)
# ------------------------------------------------------------------
@router.get("/case")
def get_or_create_preboarding_case(
    candidate_id: int = Query(...),
    jd_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns existing preboarding case or creates a new one
    with all 5 steps initialized.
    """

    # Ensure candidate is actually in PREBOARDING stage
    mapping = db.query(CandidateJDMapping).filter(
        CandidateJDMapping.candidate_id == candidate_id,
        CandidateJDMapping.jd_id == jd_id,
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Candidate not linked to JD")

    if mapping.stage != "Preboarding":
        raise HTTPException(
            status_code=400,
            detail="Candidate is not in Preboarding stage"
        )

    case = db.query(PreboardingCase).filter(
        PreboardingCase.candidate_id == candidate_id,
        PreboardingCase.jd_id == jd_id,
    ).first()

    if not case:
        case = PreboardingCase(
            candidate_id=candidate_id,
            jd_id=jd_id,
            final_status="IN_PROGRESS",
        )
        db.add(case)
        db.commit()
        db.refresh(case)

        # Initialize all steps
        for step in PREBOARDING_STEPS:
            db.add(
                PreboardingStep(
                    case_id=case.id,
                    step_type=step,
                    status="IN_PROGRESS",
                )
            )
        db.commit()

    return {
        "case_id": case.id,
        "candidate_id": case.candidate_id,
        "jd_id": case.jd_id,
        "final_status": case.final_status,
        "steps": [
            {
                "id": s.id,
                "step_type": s.step_type,
                "status": s.status,
                "verifier": s.verifier,
                "evidence_notes": s.evidence_notes,
                "discrepancy_notes": s.discrepancy_notes,
                "updated_at": s.updated_at,
            }
            for s in case.steps
        ],
    }


# ------------------------------------------------------------------
# 2️⃣ UPDATE STEP STATUS (STRICT, GATED)
# ------------------------------------------------------------------
@router.post("/step/update")
def update_preboarding_step(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Updates a single step.
    Enforces gated flow and recomputes FINAL status.
    """

    step_id = payload.get("step_id")
    new_status = payload.get("status")
    verifier = payload.get("verifier")
    evidence_notes = payload.get("evidence_notes")
    discrepancy_notes = payload.get("discrepancy_notes")

    if not step_id or new_status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid payload")

    step = db.query(PreboardingStep).filter(
        PreboardingStep.id == step_id
    ).first()

    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    # ---------------- GATING ----------------
    case_steps = (
        db.query(PreboardingStep)
        .filter(PreboardingStep.case_id == step.case_id)
        .order_by(PreboardingStep.id)
        .all()
    )

    for s in case_steps:
        if s.id == step.id:
            break
        if s.status == "FAILED":
            if user.role != "admin":
                raise HTTPException(
                    status_code=403,
                    detail="Admin override only"
                )
            break
    
    # 🚫 HARD BLOCK: CLEARED without required verified docs
    if new_status == "CLEARED" and step.step_type != "FINAL":
        required = REQUIRED_DOCS.get(step.step_type, set())

        docs = (
            db.query(PreboardingDocument)
            .filter(PreboardingDocument.step_id == step.id)
            .all()
        )

        uploaded_types = {d.doc_type for d in docs}
        verified_types = {
            d.doc_type for d in docs if d.verified == "VERIFIED"
        }

        missing = required - uploaded_types
        unverified = required - verified_types

        if missing or unverified:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Cannot mark CLEARED. "
                    "Upload and verify all required documents."
                )
            )    


    # ---------------- UPDATE STEP ----------------
    old_status = step.status  # ✅ capture BEFORE change

    step.status = new_status
    step.verifier = verifier
    step.evidence_notes = evidence_notes
    step.discrepancy_notes = discrepancy_notes
    step.updated_at = datetime.utcnow()

    # ---------------- FETCH CASE ----------------
    case = db.query(PreboardingCase).filter(
        PreboardingCase.id == step.case_id
    ).first()

    # ---------------- AUDIT LOG (SAFE) ----------------
    db.add(UserLog(
        user_id=user.id,
        action=(
            f"Preboarding step {step.step_type} "
            f"changed from {old_status} to {new_status} "
            f"(Step ID: {step.id})"
        )
    ))

    # ---------------- FINAL STATUS ----------------
    case.final_status = compute_final_status(case.steps)
    case.updated_at = datetime.utcnow()

    # ---------------- SINGLE COMMIT ----------------
    db.commit()

    return {
        "message": "Step updated",
        "step_id": step.id,
        "step_status": step.status,
        "final_status": case.final_status,
    }


# ------------------------------------------------------------------
# 3️⃣ UPLOAD / REGISTER DOCUMENT (PER STEP)
# ------------------------------------------------------------------
@router.post("/document/add")
def add_preboarding_document(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Registers a document against a step.
    (Actual file upload handled elsewhere – this stores metadata)
    """

    step_id = payload.get("step_id")
    doc_type = payload.get("doc_type")
    file_url = payload.get("file_url")

    if not all([step_id, doc_type, file_url]):
        raise HTTPException(status_code=400, detail="Missing document data")

    step = db.query(PreboardingStep).filter(
        PreboardingStep.id == step_id
    ).first()

    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    doc = PreboardingDocument(
        step_id=step_id,
        doc_type=doc_type,
        file_url=file_url,
        verified="VERIFIED",
    )

    db.add(doc)
    db.add(UserLog(
        user_id=user.id,
        action=(
            f"Uploaded document '{doc_type}' "
            f"for preboarding step '{step.step_type}' "
            f"(Step ID: {step.id})"
        )
    ))
    db.commit()
    db.refresh(doc)

    return {
        "message": "Document added",
        "document_id": doc.id,
    }


# ------------------------------------------------------------------
# 4️⃣ FINALIZE PREBOARDING (AUTO MOVE STAGE)
# ------------------------------------------------------------------
@router.post("/complete")
def complete_preboarding(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case_id = payload.get("case_id")
    if not case_id:
        raise HTTPException(400, "case_id required")

    case = db.query(PreboardingCase).filter(
        PreboardingCase.id == case_id
    ).first()

    if not case:
        raise HTTPException(404, "Preboarding case not found")

    steps = db.query(PreboardingStep).filter(
        PreboardingStep.case_id == case.id
    ).all()

    if not steps:
        raise HTTPException(400, "No preboarding steps found")

    # 🔥 1️⃣ AUTO-CLEAR FINAL STEP
    final_step = next(
        (s for s in steps if s.step_type == "FINAL"),
        None
    )

    if not final_step:
        raise HTTPException(500, "FINAL step missing")

    if final_step.status != "CLEARED":
        final_step.status = "CLEARED"
        final_step.updated_at = datetime.utcnow()

    # 🔥 2️⃣ VALIDATE ALL STEPS
    not_cleared = [s.step_type for s in steps if s.status != "CLEARED"]

    if not_cleared:
        raise HTTPException(
            status_code=409,
            detail=f"Steps not cleared: {', '.join(not_cleared)}"
        )

    # 🔥 3️⃣ MARK CASE CLEARED
    case.final_status = "CLEARED"
    case.completed_at = datetime.utcnow()

    # 🔥 4️⃣ MOVE CANDIDATE TO ONBOARDING
    mapping = db.query(CandidateJDMapping).filter(
        CandidateJDMapping.candidate_id == case.candidate_id,
        CandidateJDMapping.jd_id == case.jd_id,
    ).first()

    if not mapping:
        raise HTTPException(404, "JD mapping not found")

    mapping.stage = "Onboarding"
    mapping.updated_at = datetime.utcnow()

    db.commit()

    return {
        "message": "Preboarding completed successfully",
        "case_id": case.id,
        "final_status": case.final_status,
        "candidate_stage": mapping.stage,
    }


@router.get("/documents/{step_id}")
def get_preboarding_documents(
    step_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    docs = (
        db.query(PreboardingDocument)
        .filter(PreboardingDocument.step_id == step_id)
        .order_by(PreboardingDocument.id.desc())
        .all()
    )

    return [
        {
            "id": d.id,
            "doc_type": d.doc_type,
            "file_url": d.file_url,
            "verified": d.verified,
        }
        for d in docs
    ]

@router.post("/document/verify")
def verify_document(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc_id = payload.get("document_id")
    status = payload.get("status")  # VERIFIED / REJECTED

    if status not in ["VERIFIED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    doc = db.query(PreboardingDocument).filter(
        PreboardingDocument.id == doc_id
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.verified = status
    doc.verified_by = user.id
    doc.verified_at = datetime.utcnow()

    db.add(UserLog(
        user_id=user.id,
        action=f"Document {doc.doc_type} marked {status} (Doc ID {doc.id})"
    ))

    db.commit()

    return {
        "document_id": doc.id,
        "status": doc.verified
    }


UPLOAD_DIR = os.path.join("uploads", "preboarding")

@router.post("/document/upload")
def upload_preboarding_document(
    step_id: int = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc_type = doc_type.strip().upper()

    # ================= STEP + PERMISSION CHECK =================
    step = db.query(PreboardingStep).filter(
        PreboardingStep.id == step_id
    ).first()

    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    # 🔐 LOCKED STEP PROTECTION
    if step.status == "CLEARED":
        is_admin = user and user.role and user.role.upper() == "ADMIN"

        if not is_admin and not step.allow_user_edit:
            raise HTTPException(
                status_code=403,
                detail="Documents are locked. Admin access required."
            )

    # ================= SAVE FILE =================
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4()}{ext}"

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    disk_path = os.path.join(UPLOAD_DIR, filename)

    with open(disk_path, "wb") as f:
        f.write(file.file.read())

    file_url = f"/uploads/preboarding/{filename}"

    # ================= REPLACE LOGIC =================
    existing = db.query(PreboardingDocument).filter(
        PreboardingDocument.step_id == step_id,
        PreboardingDocument.doc_type == doc_type
    ).first()

    if existing:
        existing.file_url = file_url
        existing.verified = "VERIFIED"
        existing.uploaded_at = datetime.utcnow()
        doc = existing
    else:
        doc = PreboardingDocument(
            step_id=step_id,
            doc_type=doc_type,
            file_url=file_url,
            verified="VERIFIED",
        )
        db.add(doc)

    db.commit()
    db.refresh(doc)

    return {
        "message": "File uploaded",
        "document_id": doc.id,
        "file_url": file_url,
    }


@router.post("/step/allow-user-edit")
def allow_user_edit(
    step_id: int = Body(...),
    allow: bool = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 🔐 ADMIN ONLY
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    step = db.query(PreboardingStep).filter(
        PreboardingStep.id == step_id
    ).first()

    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    # 🔁 TOGGLE ACCESS
    step.allow_user_edit = bool(allow)
    step.updated_at = datetime.utcnow()

    # 🧾 AUDIT LOG — THIS IS NON-NEGOTIABLE
    log = UserLog(
        user_id=user.id,
        action=(
            f"Admin override: User edit "
            f"{'enabled' if allow else 'disabled'} "
            f"for step {step.step_type} "
            f"(step_id={step.id})"
        )
    )

    db.add(log)
    db.commit()

    return {
        "message": "User edit access updated",
        "step_id": step.id,
        "step_type": step.step_type,
        "allow_user_edit": step.allow_user_edit,
    }

@router.get("/step/meta/{step_id}")
def get_step_meta(
    step_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    step = db.query(PreboardingStep).filter(
        PreboardingStep.id == step_id
    ).first()

    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    return {
        "step_id": step.id,
        "step_type": step.step_type,
        "status": step.status,
        "allow_user_edit": bool(step.allow_user_edit),
    }

