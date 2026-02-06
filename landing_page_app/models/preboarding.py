from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from landing_page_app.database import Base

class PreboardingCase(Base):
    __tablename__ = "preboarding_cases"

    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, nullable=False)
    jd_id = Column(Integer, nullable=False)

    final_status = Column(String(20), default="IN_PROGRESS")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    steps = relationship("PreboardingStep", back_populates="case")


class PreboardingStep(Base):
    __tablename__ = "preboarding_steps"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("preboarding_cases.id"))

    step_type = Column(String(30))  
    # ID | EDUCATION | EXPERIENCE | REFERENCE | FINAL

    status = Column(String(20), default="IN_PROGRESS")
    allow_user_edit = Column(Boolean, default=False)
    verifier = Column(String(255), nullable=True)
    evidence_notes = Column(Text, nullable=True)
    discrepancy_notes = Column(Text, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("PreboardingCase", back_populates="steps")


class PreboardingDocument(Base):
    __tablename__ = "preboarding_documents"

    id = Column(Integer, primary_key=True)
    step_id = Column(Integer, ForeignKey("preboarding_steps.id"))

    doc_type = Column(String(100))
    file_url = Column(Text)
    verified = Column(String(20), default="PENDING")
    uploaded_at = Column(DateTime, default=datetime.utcnow)
