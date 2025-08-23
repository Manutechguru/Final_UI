from sqlalchemy import Column, Integer, String, Text
from landing_page_app.database import Base

class Candidate(Base):
    __tablename__ = "candidates"

    candidates_id = Column(Integer, primary_key=True, index=True)
    candidate_name = Column(String(255), nullable=False)
    contact = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    skillset = Column(Text, nullable=True)
    relevant_experience = Column(Text, nullable=True)
    it_experience = Column(Text, nullable=True)
    education = Column(String(255), nullable=True)
    company = Column(String(255), nullable=True)
    resumelinks = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)
    clients = Column(Text, nullable=True)  # this is previous clients worked for
    notice_period = Column(String(50), nullable=True)
