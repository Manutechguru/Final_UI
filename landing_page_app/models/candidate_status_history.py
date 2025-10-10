from sqlalchemy import Column, Integer, ForeignKey, DateTime, String
from landing_page_app.database import Base
from datetime import datetime
from sqlalchemy.orm import relationship


# The only allowed statuses for the new column
STATUS_OPTIONS = (
    "Screening", "Submissions", "Interview",
    "Offered", "Hired", "Rejected", "Archived"
)

class CandidateJDMapping(Base):
    __tablename__ = "candidate_jd_mapping"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.candidates_id"), nullable=False)
    jd_id = Column(Integer, ForeignKey("jobs.job_id"), nullable=False)
    stage = Column(String(50), default="Applied")

    # column for UI status
    status = Column(String(50), default="Screening", nullable=False)

    updated_at = Column(DateTime, default=datetime.utcnow)
    ai_score = Column(Integer, nullable=True)
   
    candidate = relationship("Candidate", backref="jd_mappings")