from pydantic import BaseModel, EmailStr
from typing import Optional

class CandidateCreate(BaseModel):
    full_name: str
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    current_location: Optional[str] = None
    total_experience: Optional[float] = None
    preferred_role: Optional[str] = None
    qualification: Optional[str] = None
    resume_link: Optional[str] = None
    parsed_resume_text: Optional[str] = None

class CandidateOut(BaseModel):
    id: int
    full_name: str
    email: Optional[EmailStr] = None
    resume_link: Optional[str] = None
    class Config:
        from_attributes = True
