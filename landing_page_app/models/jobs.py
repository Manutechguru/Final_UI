from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from landing_page_app.database import Base
from datetime import datetime


class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(Integer, primary_key=True, index=True)
    manager_id = Column(Integer, ForeignKey("managers.manager_id", ondelete="CASCADE"), nullable=False)

    job_title = Column(String(255), nullable=False)
    job_description = Column(String, nullable=True)
    status = Column(String(10), default="active")

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationship
    manager = relationship("Manager", back_populates="jobs")
