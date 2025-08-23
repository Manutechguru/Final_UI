from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from landing_page_app.database import Base
from datetime import datetime

class Client(Base):
    __tablename__ = "clients"

    client_id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(10), default="active")  # <-- Added status column

    # Relationship to Job model
    jobs = relationship("Job", back_populates="client")  # <-- keeps the jobs relationship