from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from landing_page_app.database import Base
from datetime import datetime

class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.client_id", ondelete="CASCADE"), nullable=True)
    manager_id = Column(Integer, ForeignKey("managers.manager_id", ondelete="CASCADE"), nullable=True)

    job_title = Column(String(255), nullable=True)
    job_description = Column(String, nullable=True)
    status = Column(String(10), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    # ✅ Relationships
    client = relationship("Client", back_populates="jobs")
    manager = relationship("Manager", back_populates="jobs")