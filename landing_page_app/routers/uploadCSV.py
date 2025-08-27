from fastapi import APIRouter, Request, Depends, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from urllib.parse import quote_plus

from landing_page_app.database import get_db
from landing_page_app.crud.insertCandidates import insert_candidates_from_csv

router = APIRouter()

@router.post("/admin/upload-csv")
async def upload_csv(
    request: Request,
    csv_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # Basic check
    if not csv_file.filename.lower().endswith(".csv"):
        err = quote_plus("Please upload a valid CSV file")
        return RedirectResponse(url=f"/admin?tab=uploadcsv&error={err}", status_code=303)

    try:
        result = insert_candidates_from_csv(db, csv_file)
        msg = quote_plus(result.get("message", "Upload complete"))
        dups = ",".join(result.get("duplicates", [])) if result.get("duplicates") else ""
        # ✅ Stay on Upload CSV tab and show only one message area
        return RedirectResponse(
            url=f"/admin?tab=uploadcsv&msg={msg}&duplicates={quote_plus(dups)}",
            status_code=303
        )
    except Exception as e:
        err = quote_plus(f"Upload failed: {str(e)}")
        # ✅ On error, also keep user on the same tab
        return RedirectResponse(url=f"/admin?tab=uploadcsv&error={err}", status_code=303)
