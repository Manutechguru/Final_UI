from pydantic import BaseModel, EmailStr
from typing import Optional

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
