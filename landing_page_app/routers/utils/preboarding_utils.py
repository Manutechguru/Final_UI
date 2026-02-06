# landing_page_app/routers/utils/preboarding_utils.py

"""
Pure preboarding business rules.
NO FastAPI
NO DB session
NO side effects

This file must remain:
- deterministic
- testable
- reusable
"""

# ---------------------------------------------------------
# CONSTANTS (single source of truth)
# ---------------------------------------------------------

PREBOARDING_STEPS_ORDER = [
    "ID",
    "EDUCATION",
    "EXPERIENCE",
    "REFERENCE",
    "FINAL",
]

ALLOWED_STEP_STATUSES = {
    "CLEARED",
    "IN_PROGRESS",
    "FAILED",
}

FINAL_STATUS_VALUES = {
    "CLEARED",
    "IN_PROGRESS",
    "FAILED",
}


# ---------------------------------------------------------
# 1️⃣ FINAL STATUS COMPUTATION (STRICT LOGIC)
# ---------------------------------------------------------
def compute_final_status(steps):
    """
    Decision Logic (STRICT):

    - If ANY step = FAILED → FINAL = FAILED
    - Else if ALL steps = CLEARED → FINAL = CLEARED
    - Else → FINAL = IN_PROGRESS
    """

    statuses = [s.status for s in steps]

    if any(status == "FAILED" for status in statuses):
        return "FAILED"

    if all(status == "CLEARED" for status in statuses):
        return "CLEARED"

    return "IN_PROGRESS"


# ---------------------------------------------------------
# 2️⃣ STEP ORDER VALIDATION
# ---------------------------------------------------------
def is_step_order_valid(current_step_type, previous_steps):
    """
    Ensures gated flow:
    - A step cannot be updated if ANY previous step FAILED
    """

    for step in previous_steps:
        if step.step_type == current_step_type:
            break
        if step.status == "FAILED":
            return False

    return True


# ---------------------------------------------------------
# 3️⃣ STEP STATUS VALIDATION
# ---------------------------------------------------------
def validate_step_status_transition(old_status, new_status):
    """
    Prevents illegal transitions.

    Allowed:
    - IN_PROGRESS → CLEARED
    - IN_PROGRESS → FAILED
    - CLEARED → FAILED (admin override use-case)
    - FAILED → IN_PROGRESS (admin override / recheck)

    Disallowed:
    - CLEARED → IN_PROGRESS (unless admin explicitly allows)
    """

    if new_status not in ALLOWED_STEP_STATUSES:
        return False

    if old_status == new_status:
        return True

    # Strict default rules
    allowed_transitions = {
        "IN_PROGRESS": {"CLEARED", "FAILED"},
        "CLEARED": {"FAILED"},      # downgrade only
        "FAILED": {"IN_PROGRESS"},  # retry
    }

    return new_status in allowed_transitions.get(old_status, set())


# ---------------------------------------------------------
# 4️⃣ DOCUMENT REQUIREMENTS PER STEP
# ---------------------------------------------------------
def required_documents_for_step(step_type):
    """
    Defines mandatory documents for each step.
    Used by frontend + backend validation.
    """

    return {
        "ID": [
            "AADHAAR_OR_PASSPORT",
            "PAN_CARD",
            "ADDRESS_PROOF",
            "PASSPORT_PHOTO",
        ],
        "EDUCATION": [
            "DEGREE_CERTIFICATE",
            "ALL_SEM_MARKSHEETS",
            "INTERMEDIATE_CERTIFICATE",
            "SSC_10TH_CERTIFICATE",
        ],
        "EXPERIENCE": [
            "OFFER_LETTERS",
            "RELIEVING_LETTERS",
            "PAYSLIPS_LAST_3_6",
            "PF_UAN_NUMBER",
        ],
        "REFERENCE": [
            "REFERENCE_1",
            "REFERENCE_2",
        ],
    }.get(step_type, [])


# ---------------------------------------------------------
# 5️⃣ STEP COMPLETION CHECK (DOCUMENT-BASED)
# ---------------------------------------------------------
def is_step_ready_for_clearance(step_type, documents):
    """
    Returns True ONLY if all required documents exist
    and are VERIFIED.
    """

    required_docs = set(required_documents_for_step(step_type))
    if not required_docs:
        return True

    provided_verified_docs = {
        d.doc_type
        for d in documents
        if d.verified == "VERIFIED"
    }

    return required_docs.issubset(provided_verified_docs)


# ---------------------------------------------------------
# 6️⃣ HUMAN-READABLE SUMMARY (FINAL CHEVRON)
# ---------------------------------------------------------
def build_final_summary(steps, documents_by_step):
    """
    Builds a structured summary for FINAL step display.
    Pure transformation, no DB calls.
    """

    summary = []

    for step in steps:
        step_docs = documents_by_step.get(step.id, [])

        summary.append({
            "step_type": step.step_type,
            "status": step.status,
            "verifier": step.verifier,
            "evidence_notes": step.evidence_notes,
            "discrepancy_notes": step.discrepancy_notes,
            "documents": [
                {
                    "doc_type": d.doc_type,
                    "verified": d.verified,
                    "file_url": d.file_url,
                }
                for d in step_docs
            ],
        })

    return summary
