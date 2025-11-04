# landing_page_app/routers/candidates/downloads.py
from fastapi import APIRouter, Query, HTTPException, Depends, Body, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import logging
import io
import zipfile
import re
from pathlib import Path
from typing import List, Tuple, Optional

from landing_page_app.database import get_db
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.candidate_status_history import CandidateJDMapping
from landing_page_app.models.clients import Client
from landing_page_app.models.jobs import Job
from landing_page_app.models.managers import Manager

# storage helpers (existing in your repo; handle Drive/raw binary download and candidate folder paths)
from landing_page_app.routers.utils.storage_utils import _candidate_folder, _download_binary
# xlsx util
from landing_page_app.routers.utils.xlsx_utils import create_xlsx

router = APIRouter(prefix="/candidates", tags=["Candidate Downloads"])

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# -----------------------
# Try to import get_current_user (robust fallback)
# -----------------------
try:
    # primary location used elsewhere in your project
    from landing_page_app.routers.auth import get_current_user
except Exception:
    try:
        from landing_page_app.auth.dependencies import get_current_user
    except Exception:
        try:
            from landing_page_app.dependencies import get_current_user
        except Exception:
            # fallback no-op dependency if not available
            def get_current_user():
                return None


# -----------------------
# Try to import add_user_log; fallback to noop
# -----------------------
try:
    from landing_page_app.models.log import add_user_log
except Exception:
    def add_user_log(db: Session, user_id: int, action: str, commit: bool = False):
        return None


def _slugify_filename(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r'[^A-Za-z0-9_\-\.]+', '-', s)
    return s.strip('-') or "file"


def _build_resume_zip_from_candidates(rows: List[Candidate], client: Client, job: Job) -> Tuple[io.BytesIO, str]:
    """
    Build a ZIP file in memory for the given candidate rows.
    Handles:
      - remote resume URLs via _download_binary (supports Drive links)
      - local files inside the candidate folder (_candidate_folder)
    Raises HTTPException(404) if no resume files are found for the provided candidates.
    Returns: (BytesIO, zip_filename)
    """
    zip_buffer = io.BytesIO()
    total_files = 0

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for c in rows:
            # candidate id normalization
            cid = getattr(c, "candidates_id", getattr(c, "candidate_id", None))
            if cid is None:
                continue
            prefix = str(cid)

            # 1) Try remote resume link attributes (common names)
            resume_url = None
            for attr in ("resumelinks", "resume", "resume_link", "resumelink"):
                if hasattr(c, attr):
                    val = getattr(c, attr)
                    if val:
                        resume_url = val
                        break

            candidate_added = 0

            if resume_url and isinstance(resume_url, str) and resume_url.strip():
                try:
                    # _download_binary expected to return (bytes, suggested_name)
                    data, suggested_name = _download_binary(resume_url)
                    if data:
                        ext = Path(suggested_name or "resume.pdf").suffix or ".pdf"
                        filename = f"resume{ext}"
                        arcname = f"{prefix}/{filename}"
                        zf.writestr(arcname, data)
                        candidate_added += 1
                        total_files += 1
                except Exception as e:
                    logger.exception("Failed to download resume for candidate %s from URL %s : %s", cid, resume_url, e)

            # 2) Try local candidate folder if nothing added for this candidate
            if candidate_added == 0:
                try:
                    folder = _candidate_folder(client.client_name, client.client_id, job.job_title, job.job_id, cid)
                except Exception:
                    folder = None

                if folder:
                    folder_path = Path(folder)
                else:
                    folder_path = None

                if folder_path and folder_path.exists():
                    resume_latest = folder_path / "resume-latest"
                    resume_files = []
                    if resume_latest.exists() and resume_latest.is_dir():
                        resume_files = list(resume_latest.glob("resume*"))
                    if not resume_files:
                        resume_files = list(folder_path.glob("resume*"))

                    # Fallback: include common file types in the folder
                    if not resume_files:
                        resume_files = [p for p in folder_path.iterdir() if p.is_file() and p.suffix.lower() in {'.pdf', '.docx', '.doc', '.txt'}]

                    for file in resume_files:
                        try:
                            zf.write(str(file), arcname=f"{prefix}/{file.name}")
                            candidate_added += 1
                            total_files += 1
                        except Exception as e:
                            logger.exception("Failed to add local resume %s for candidate %s: %s", file, cid, e)

            # if neither remote nor local resumes found for this candidate, log and continue
            if candidate_added == 0:
                logger.debug("No resume found for candidate %s (skipping)", cid)

    if total_files == 0:
        raise HTTPException(status_code=404, detail="No resumes found for the selected candidates")

    zip_buffer.seek(0)
    safe_title = _slugify_filename(job.job_title)
    zip_filename = f"{job.job_id}-{safe_title}-resumes.zip"
    return zip_buffer, zip_filename


# ----------------------------------------------------------------------
# DOWNLOAD SELECTED RESUMES AS ZIP (GET with query params; matches frontend)
# ----------------------------------------------------------------------
@router.get("/download/resumes")
def download_resumes_zip(
    request: Request,
    candidate_ids: str = Query(..., description="Comma-separated candidate IDs"),
    jd_id: int = Query(..., description="Job/ JD ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        ids = [int(x) for x in candidate_ids.split(",") if x.strip()]
        if not ids:
            raise HTTPException(status_code=400, detail="No candidate IDs provided")

        # Fetch job/jd
        job = db.query(Job).filter(Job.job_id == jd_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="JD not found")

        # Fetch manager for this job (Job has manager_id)
        manager = db.query(Manager).filter(Manager.manager_id == getattr(job, "manager_id", None)).first()
        if not manager:
            raise HTTPException(status_code=404, detail="Manager not found for JD")

        # Fetch client from manager
        client = db.query(Client).filter(Client.client_id == getattr(manager, "client_id", None)).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found for JD")

        # Fetch candidate rows (only those requested)
        rows = db.query(Candidate).filter(Candidate.candidates_id.in_(ids)).all()
        if not rows:
            raise HTTPException(status_code=404, detail="No candidates found for provided IDs")

        # Build ZIP in memory (handles remote + local resumes)
        zip_buffer, zip_filename = _build_resume_zip_from_candidates(rows, client, job)

        # -------------------------
        # Log the action BEFORE returning the stream
        # -------------------------
        try:
            # actor friendly name
            actor = getattr(current_user, "full_name", None) or getattr(current_user, "name", None) or getattr(current_user, "email", None) or "Unknown User"
            # use candidate names if available, fallback to ids
            cand_names = []
            for c in rows:
                name = getattr(c, "candidate_name", None) or getattr(c, "name", None)
                if name:
                    cand_names.append(str(name))
                else:
                    cid = getattr(c, "candidates_id", getattr(c, "candidate_id", None))
                    cand_names.append(str(cid) if cid is not None else "unknown")

            names_str = ", ".join(cand_names)
            log_msg = f"{actor} downloaded resumes as ZIP for candidates: {names_str}"
            add_user_log(db, getattr(current_user, "id", None), log_msg)
            try:
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
        except Exception as log_exc:
            logger.warning("Failed to record download-resumes log: %s", log_exc)
            try:
                db.rollback()
            except Exception:
                pass

        headers = {"Content-Disposition": f"attachment; filename={zip_filename}"}
        return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error while creating resumes ZIP: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while creating ZIP")


# ----------------------------------------------------------------------
# EXPORT SELECTED CANDIDATES (POST /export/xlsx) — uses same columns
# ----------------------------------------------------------------------
@router.post("/export/xlsx")
def export_selected_candidates(
    request: Request,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        candidate_ids = body.get("candidate_ids", [])
        if not candidate_ids:
            raise HTTPException(status_code=400, detail="No candidate IDs provided")

        rows = db.query(Candidate).filter(Candidate.candidates_id.in_(candidate_ids)).all()
        if not rows:
            raise HTTPException(status_code=404, detail="No candidates found for provided IDs")

        data = []
        for c in rows:
            # Build a dict with keys that exactly match the columns below.
            data.append({
                "Candidate ID": getattr(c, "candidates_id", getattr(c, "candidate_id", "")),
                "Candidate Name": getattr(c, "candidate_name", getattr(c, "name", "")),
                "Contact": getattr(c, "contact", ""),
                "Skills": getattr(c, "skillset", getattr(c, "skills", "")) or "",
                "Email": getattr(c, "email", ""),
                "Location": getattr(c, "location", ""),
                "Company": getattr(c, "company", ""),
                "Relevant Experience": (
                    getattr(c, "relevant_experience", "")
                    or getattr(c, "relevant_exp", "")
                    or getattr(c, "rel_exp", "")
                    or getattr(c, "Rel_Exp", "")
                    or getattr(c, "Rel Exp", "")
                    or getattr(c, "experience", "")
                ) or "",
                "IT Experience": getattr(c, "it_experience", "") or "",
                "CTC": getattr(c, "ctc", "") or "",
                "ECTC": getattr(c, "expected_ctc", "") or getattr(c, "ectc", "") or "",
                "Notice Period": getattr(c, "notice_period", "") or "",
                "Joining Location": getattr(c, "joining_location", "") or "",
                "Offer In Any": getattr(c, "offer_in_any", "") or "",
                "Remarks": getattr(c, "remarks", getattr(c, "comment", "")) or ""
            })

        # IMPORTANT: Columns list must match the keys used above (order matters for XLSX)
        columns = [
            "Candidate ID", "Candidate Name", "Contact", "Skills", "Email", "Location", "Company",
            "Relevant Experience", "IT Experience", "CTC", "ECTC", "Notice Period",
            "Joining Location", "Offer In Any", "Remarks"
        ]

        # Create XLSX stream using the robust create_xlsx helper (writes headers explicitly)
        xlsx_stream = create_xlsx(data, columns, sheet_name="Selected Candidates")
        xlsx_stream.seek(0)

        # -------------------------
        # Log the action BEFORE returning the stream
        # -------------------------
        try:
            actor = getattr(current_user, "full_name", None) or getattr(current_user, "name", None) or getattr(current_user, "email", None) or "Unknown User"
            cand_names = []
            for c in rows:
                name = getattr(c, "candidate_name", None) or getattr(c, "name", None)
                if name:
                    cand_names.append(str(name))
                else:
                    cid = getattr(c, "candidates_id", getattr(c, "candidate_id", None))
                    cand_names.append(str(cid) if cid is not None else "unknown")

            names_str = ", ".join(cand_names)
            log_msg = f"{actor} exported candidate details to XLSX for: {names_str}"
            add_user_log(db, getattr(current_user, "id", None), log_msg)
            try:
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
        except Exception as log_exc:
            logger.warning("Failed to record export-xlsx log: %s", log_exc)
            try:
                db.rollback()
            except Exception:
                pass

        headers = {"Content-Disposition": "attachment; filename=selected_candidates.xlsx"}
        return StreamingResponse(
            xlsx_stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error exporting selected candidates XLSX: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error while exporting selected candidates")
