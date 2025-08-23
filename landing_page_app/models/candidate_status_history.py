from sqlalchemy import Column, Integer, ForeignKey, DateTime, String
from landing_page_app.database import Base
from datetime import datetime

class CandidateJDMapping(Base):
    __tablename__ = "candidate_jd_mapping"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.candidates_id"), nullable=False)
    jd_id = Column(Integer, ForeignKey("jobs.job_id"), nullable=False)   # <-- updated
    stage = Column(String(50), default="Applied")
    updated_at = Column(DateTime, default=datetime.utcnow)
    ai_score = Column(Integer, nullable=True)

