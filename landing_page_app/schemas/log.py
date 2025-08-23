from pydantic import BaseModel
from datetime import datetime

class UserLogOut(BaseModel):
    id: int
    email: str
    full_name: str
    action: str
    timestamp: datetime

    class Config:
        orm_mode = True 