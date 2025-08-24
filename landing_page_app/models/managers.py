from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from landing_page_app.database import Base
from datetime import datetime

class Manager(Base):
    __tablename__ = "managers"

    manager_id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.client_id", ondelete="CASCADE"), nullable=False)
    manager_name = Column(String(255), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(String(255), nullable=True)

    # ✅ Relationship back to client
    client = relationship("Client", back_populates="managers")

    # ✅ Jobs uploaded under this manager
    jobs = relationship("Job", back_populates="manager", cascade="all, delete-orphan")