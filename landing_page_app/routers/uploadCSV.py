# landing_page_app/routers/uploadCSV.py
from fastapi import APIRouter, Request, Depends, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from landing_page_app.database import get_db
from landing_page_app.crud import insertCandidates

router = APIRouter()

@router.post("/admin/upload-csv")
async def upload_csv(
    request: Request,
    csv_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not csv_file.filename.endswith(".csv"):
        return RedirectResponse(url="/admin?error=Please+upload+a+valid+CSV+file", status_code=303)

    try:
        result = insertCandidates.insert_candidates_from_csv(db, csv_file)

        # Pass duplicates as query string (joined by commas)
        dup_names = ",".join(result["duplicates"]) if result["duplicates"] else ""
        return RedirectResponse(
            url=f"/admin?msg={result['message']}&duplicates={dup_names}",
            status_code=303
        )
    except Exception as e:
        return RedirectResponse(url=f"/admin?error=Upload+failed:+{str(e)}", status_code=303)
