from typing import List, Dict
from fastapi import HTTPException


# ============================================================
# CANONICAL ONBOARDING FLOW (DO NOT REORDER)
# ============================================================

ONBOARDING_STEPS = [
    "JOINING_DETAILS",
    "PAYROLL",
    "IT_ACCESS",
    "POLICY",
    "FINAL"
]


VALID_STATUSES = {"IN_PROGRESS", "CLEARED", "FAILED"}


# ============================================================
# STEP POSITION HELPERS
# ============================================================

def step_index(step_type: str) -> int:
    if step_type not in ONBOARDING_STEPS:
        raise HTTPException(400, f"Invalid onboarding step: {step_type}")
    return ONBOARDING_STEPS.index(step_type)


def previous_steps(all_steps, step_type: str):
    idx = step_index(step_type)
    return [s for s in all_steps if step_index(s.step_type) < idx]


def next_steps(all_steps, step_type: str):
    idx = step_index(step_type)
    return [s for s in all_steps if step_index(s.step_type) > idx]


# ============================================================
# HARD STOP RULE
# ============================================================

def ensure_no_previous_failure(all_steps, step_type: str):
    for step in previous_steps(all_steps, step_type):
        if step.status == "FAILED":
            raise HTTPException(
                400,
                f"Onboarding locked. Step '{step.step_type}' already FAILED."
            )


# ============================================================
# STEP-LEVEL VALIDATION RULES
# ============================================================

def validate_joining_details(data: Dict):
    required_fields = {
        "date_of_joining": str,
        "work_location": str,
        "employment_type": str,
        "shift_timings": str,
        "reporting_manager_id": int,
        "client_id": int,
        "candidate_confirmed": bool,
    }

    for field, expected_type in required_fields.items():
        if field not in data:
            raise HTTPException(
                status_code=422,
                detail=f"Missing field: {field}"
            )

        value = data[field]

        # Null / empty checks
        if value is None:
            raise HTTPException(
                status_code=422,
                detail=f"Null value for field: {field}"
            )

        if expected_type == str and value.strip() == "":
            raise HTTPException(
                status_code=422,
                detail=f"Empty string for field: {field}"
            )

        # Strict type check (bool handled separately)
        if expected_type == bool:
            if value is not True:
                raise HTTPException(
                    status_code=422,
                    detail="Candidate must confirm availability"
                )
        else:
            if not isinstance(value, expected_type):
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid type for {field}. Expected {expected_type.__name__}"
                )

def validate_payroll(data: Dict):
    required_fields = [
        "bank_account_holder",
        "bank_name",
        "ifsc_code",
        "account_number",
        "pf_option",
        "esic_applicable",
        "salary_acknowledged"
    ]

    for field in required_fields:
        if data.get(field) in [None, ""]:
            raise HTTPException(400, f"Missing Payroll Field: {field}")

    if data.get("salary_acknowledged") is not True:
        raise HTTPException(
            400,
            "Salary structure must be acknowledged"
        )


def validate_it_access(data: Dict):
    required_fields = [
        "official_email",
        "asset_required",
        "email_created"
    ]

    for field in required_fields:
        if field not in data:
            raise HTTPException(400, f"Missing IT Field: {field}")

    if data.get("asset_required") is True and not data.get("asset_id"):
        raise HTTPException(
            400,
            "Asset ID required when asset is marked as required"
        )


def validate_policy(data: Dict):
    required_flags = [
        "offer_letter_accepted",
        "nda_signed",
        "employment_agreement_signed"
    ]

    for flag in required_flags:
        if data.get(flag) is not True:
            raise HTTPException(
                400,
                f"Policy acknowledgement missing: {flag}"
            )


def validate_final(data: Dict):
    # Final step is READ-ONLY summary
    return True


# ============================================================
# MASTER VALIDATOR
# ============================================================

def validate_step_data(step_type: str, data: Dict):
    if not isinstance(data, dict):
        raise HTTPException(400, "Invalid step data format")

    if step_type == "JOINING_DETAILS":
        validate_joining_details(data)

    elif step_type == "PAYROLL":
        validate_payroll(data)

    elif step_type == "IT_ACCESS":
        validate_it_access(data)

    elif step_type == "POLICY":
        validate_policy(data)

    elif step_type == "FINAL":
        validate_final(data)

    else:
        raise HTTPException(400, "Unknown onboarding step")


# ============================================================
# FINAL STATUS COMPUTATION (ABSOLUTE TRUTH)
# ============================================================

def compute_onboarding_status(steps) -> str:
    """
    Rules:
    - ANY FAILED → FAILED
    - ALL CLEARED → COMPLETED
    - ELSE → IN_PROGRESS
    """

    statuses = [s.status for s in steps]

    if "FAILED" in statuses:
        return "FAILED"

    if all(status == "CLEARED" for status in statuses):
        return "COMPLETED"

    return "IN_PROGRESS"


# ============================================================
# STATUS CHANGE GUARD
# ============================================================

def validate_status_transition(step, new_status: str):
    if new_status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status: {new_status}")

    # No resurrection unless admin override
    if step.status == "FAILED" and new_status != "FAILED":
        raise HTTPException(
            400,
            "FAILED step cannot be changed without admin override"
        )
