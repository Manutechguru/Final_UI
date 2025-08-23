from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from landing_page_app.database import Base
from datetime import datetime

class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.client_id"), nullable=False)
    job_title = Column(String(255), nullable=False)
    job_description = Column(String, nullable=True)  # Google Drive link
    status = Column(String(50), default="active")  # <-- NEW COLUMN
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="jobs")
