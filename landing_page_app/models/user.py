from sqlalchemy import Boolean, Column, Integer, String, Enum
from landing_page_app.database import Base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum



class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=False)  # Pending approval
    created_at = Column(String, server_default=func.now())
