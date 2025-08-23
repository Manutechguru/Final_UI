from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

# ----------------------
# Client Schemas
# ----------------------
class ClientCreate(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None

class ClientOut(BaseModel):
    id: int
    name: str
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    company: Optional[str] = None

    class Config:
        from_attributes = True

# ----------------------
# Job Schemas
# ----------------------
class JobBase(BaseModel):
    title: str
    description: Optional[str] = None
    client_id: int  # foreign key to clients table

class JobCreate(JobBase):
    pass  # same fields as JobBase

class JobOut(JobBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
