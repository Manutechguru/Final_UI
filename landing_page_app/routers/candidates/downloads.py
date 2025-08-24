from fastapi import APIRouter, Body, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List

from landing_page_app.database import get_db
from landing_page_app.models.candidates import Candidate
from landing_page_app.routers.utils.file_utils import build_resume_zip
from landing_page_app.routers.utils.xlsx_utils import export_jobs_xlsx

router = APIRouter(prefix="/candidates", tags=["Candidate Downloads"])


# ----------------------------------------------------------------------
# DOWNLOAD MULTIPLE RESUMES AS ZIP
# ----------------------------------------------------------------------
@router.post("/download/resumes")
def download_resumes_zip(
    candidate_ids: List[int] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Build and return a ZIP file containing candidate resumes.
    Uses file_utils.create_zip_from_resumes().
    """
    rows = db.query(Candidate).filter(Candidate.candidates_id.in_(candidate_ids)).all()

    if not rows:
        raise HTTPException(status_code=404, detail="No candidates found")

    zip_path =  build_resume_zip(rows)
    return FileResponse(
        zip_path,
        filename="resumes.zip",
        media_type="application/zip"
    )


# ----------------------------------------------------------------------
# EXPORT ALL CANDIDATES TO XLSX
# ----------------------------------------------------------------------
@router.get("/export/xlsx")
def export_candidates(db: Session = Depends(get_db)):
    """
    Export all candidates to XLSX.
    Uses utils.xlsx_utils.export_candidates_to_xlsx().
    """
    rows = db.query(Candidate).order_by(Candidate.candidates_id.desc()).all()

    if not rows:
        raise HTTPException(status_code=404, detail="No candidates available for export")

    xlsx_path = export_jobs_xlsx(rows)
    return FileResponse(
        xlsx_path,
        filename="candidates.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
