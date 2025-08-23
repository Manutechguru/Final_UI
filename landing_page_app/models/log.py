from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func
from landing_page_app.database import Base

class UserLog(Base):
    __tablename__ = "user_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    action = Column(String, nullable=False)  # e.g., LOGIN, SIGNUP, APPROVED
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
