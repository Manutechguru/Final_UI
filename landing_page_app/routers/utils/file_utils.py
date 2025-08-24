# landing_page_app/utils/file_utils.py
import os
import io
import zipfile
from pathlib import Path
from typing import List, Tuple

from .storage_utils import _candidate_folder, _download_binary


# -----------------------------
# ZIP Helper: Pack candidate resumes
# -----------------------------
def build_resume_zip(
    client_name: str, client_id: int,
    job_title: str, job_id: int,
    candidate_ids: List[int]
) -> Tuple[io.BytesIO, str]:
    """
    Create an in-memory ZIP containing resumes for selected candidates.
    Returns (BytesIO, zip_filename).
    """
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for cid in candidate_ids:
            folder = _candidate_folder(client_name, client_id, job_title, job_id, cid)

            # look for resume files in the candidate folder
            if not folder.exists():
                continue

            # We prefer "resume-latest/resume.ext" if exists, else fallback
            resume_latest = folder / "resume-latest"
            resume_files = list(resume_latest.glob("resume*")) or list(folder.glob("resume*"))

            if not resume_files:
                continue

            for file in resume_files:
                arcname = f"{cid}/{file.name}"  # inside zip: candidateId/resume.pdf
                zf.write(file, arcname)

    zip_buffer.seek(0)

    zip_filename = f"{job_id}-{job_title.lower().replace(' ', '-')}-resumes.zip"
    return zip_buffer, zip_filename


# -----------------------------
# Direct download helper
# -----------------------------
def fetch_and_cache_resume(resume_url: str, target_folder: Path) -> Path:
    """
    Download a resume from Drive/URL and save into a provided folder.
    Returns the saved file path.
    """
    data, suggested_name = _download_binary(resume_url)
    ext = Path(suggested_name).suffix or ".pdf"
    target = target_folder / f"resume{ext}"
    target_folder.mkdir(parents=True, exist_ok=True)

    with open(target, "wb") as f:
        f.write(data)

    return target
