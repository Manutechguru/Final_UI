# landing_page_app/deps.py
from fastapi import Depends, Cookie, HTTPException
from sqlalchemy.orm import Session

from landing_page_app.database import get_db
from landing_page_app.models.user import User

def get_current_user(
    user_email: str | None = Cookie(None),
    db: Session = Depends(get_db),
) -> User:
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user