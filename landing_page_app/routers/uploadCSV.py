# REPLACE THE WHOLE FILE WITH THIS CONTENT

from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, Request, UploadFile, File, Cookie
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from landing_page_app.database import get_db
from landing_page_app.crud.insertCandidates import insert_candidates_from_csv
from landing_page_app.models.log import UserLog
from landing_page_app.models.user import User

router = APIRouter(tags=["Upload CSV"])

@router.post("/admin/upload", include_in_schema=False)
async def upload_csv(
    request: Request,
    csv_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_email: str | None = Cookie(None),
):
    """
    Handles CSV upload of candidates (admin-only UI).
    Also logs the upload action to UserLog for the acting admin.
    """
    try:
        result = insert_candidates_from_csv(db, csv_file)
        msg = quote_plus(result.get("message", "Upload complete"))

        # Log the activity for auditing
        try:
            admin = db.query(User).filter(User.email == (user_email or "")).first()
            if admin:
                inserted = result.get("inserted", None)
                dups = result.get("duplicates", []) or []
                detail = f"UPLOAD_CSV inserted={inserted if inserted is not None else 'NA'} duplicates={len(dups)}"
                db.add(UserLog(user_id=admin.id, action=detail))
                db.commit()
        except Exception:
            db.rollback()  # don't break user flow if logging fails

        return RedirectResponse(
            url=f"/admin?tab=upload&info={msg}",
            status_code=303,
        )
    except Exception as e:
        err = quote_plus(str(e))
        return RedirectResponse(
            url=f"/admin?tab=upload&error={err}",
            status_code=303,
        )
