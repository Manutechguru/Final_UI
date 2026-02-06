from sqlalchemy import (Column, Integer, String, DateTime, ForeignKey, Text, JSON)
from sqlalchemy.orm import relationship
from datetime import datetime
from landing_page_app.database import Base
from sqlalchemy import Boolean   # 👈 ADD THIS IMPORT


# ============================
# ONBOARDING CASE (1 per JD + Candidate)
# ============================
class OnboardingCase(Base):
    __tablename__ = "onboarding_cases"

    id = Column(Integer, primary_key=True, index=True)

    candidate_id = Column(Integer, nullable=False, index=True)
    jd_id = Column(Integer, nullable=False, index=True)

    # IN_PROGRESS | COMPLETED | FAILED
    final_status = Column(String(20), nullable=False, default="IN_PROGRESS")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    steps = relationship(
        "OnboardingStep",
        back_populates="case",
        cascade="all, delete-orphan",
        lazy="select"
    )


# ============================
# EACH CHEVRON = ONE STEP
# ============================
class OnboardingStep(Base):
    __tablename__ = "onboarding_steps"

    id = Column(Integer, primary_key=True, index=True)

    case_id = Column(
        Integer,
        ForeignKey("onboarding_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # JOINING_DETAILS | PAYROLL | IT_ACCESS | POLICY | FINAL
    step_type = Column(String(50), nullable=False, index=True)

    # IN_PROGRESS | CLEARED | FAILED
    status = Column(String(20), nullable=False, default="IN_PROGRESS")

    # ALL form fields, radio, checkbox, dropdown values
    # Example:
    # {
    #   "doj": "2026-02-01",
    #   "work_location": "Remote",
    #   "pf_opt_in": true,
    #   "bank_verified": true
    # }
    data = Column(JSON, nullable=True)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    case = relationship("OnboardingCase", back_populates="steps")
    documents = relationship(
        "OnboardingDocument",
        back_populates="step",
        cascade="all, delete-orphan",
        lazy="select"
    )


# ============================
# DOCUMENTS (CHEQUE, ETC.)
# ============================
class OnboardingDocument(Base):
    __tablename__ = "onboarding_documents"

    id = Column(Integer, primary_key=True, index=True)

    step_id = Column(
        Integer,
        ForeignKey("onboarding_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    doc_type = Column(String(100), nullable=False)
    file_url = Column(Text, nullable=False)

    # VERIFIED | REJECTED | PENDING
    verified = Column(String(20), nullable=False, default="VERIFIED")

    # 🔥 ADD THESE TWO LINES (CRITICAL)
    is_active = Column(Boolean, default=True, nullable=False)
    replaced_at = Column(DateTime, nullable=True)

    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    step = relationship("OnboardingStep", back_populates="documents")
