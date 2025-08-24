# landing_page_app/utils/storage_utils.py
import os
import re
import json
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

import requests


# ---------------------------
# Config & path helpers
# ---------------------------
def _app_root() -> Path:
    # utils/ -> landing_page_app/
    return Path(__file__).resolve().parents[1]

def _storage_root() -> Path:
    # Allow override via env; default: landing_page_app/storage
    root = os.getenv("STORAGE_ROOT", str(_app_root() / "storage"))
    p = Path(root)
    p.mkdir(parents=True, exist_ok=True)
    return p

def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s-]+", "", s)          # remove non word/space/hyphen
    s = re.sub(r"\s+", "-", s).strip("-")    # spaces -> hyphens
    return s or "na"


def _candidate_folder(
    client_name: str, client_id: int,
    job_title: str, job_id: int,
    candidate_id: int
) -> Path:
    root = _storage_root()
    client_dir = f"{client_id}-{_slug(client_name)}"
    job_dir = f"{job_id}-{_slug(job_title)}"
    cand_dir = f"{candidate_id}"
    folder = root / "clients" / client_dir / job_dir / "candidates" / cand_dir
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ---------------------------
# Drive helpers (best-effort)
# ---------------------------
def _normalize_drive_link(url: str) -> str:
    """Turn Google Drive/Docs URLs into direct-download where possible."""
    s = (url or "").strip()
    if not s:
        return s

    # Google Docs -> export as DOCX (keeps formatting better than txt for resumes)
    m_doc = re.search(r"https://docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", s)
    if m_doc:
        file_id = m_doc.group(1)
        return f"https://docs.google.com/document/d/{file_id}/export?format=docx"

    # /file/d/<id>/
    m_file = re.search(r"/d/([a-zA-Z0-9_-]+)", s)
    if m_file:
        file_id = m_file.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    # open?id=<id>
    m_open = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", s)
    if m_open:
        file_id = m_open.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    return s


# ---------------------------
# Download logic
# ---------------------------
def _guess_filename_and_ext(url: str, resp: requests.Response) -> Tuple[str, str]:
    """Return (filename, extension) using URL, headers, or fallback."""
    # Content-Disposition
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
    if m:
        fname = m.group(1)
        ext = Path(fname).suffix or ""
        return fname, ext

    # URL
    url_name = Path(re.sub(r"[?#].*$", "", url)).name  # strip query/frag
    if url_name:
        ext = Path(url_name).suffix
        if ext:
            return url_name, ext

    # Content-Type
    ctype = (resp.headers.get("Content-Type") or "").lower()
    ext_map = {
        "application/pdf": ".pdf",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "text/plain": ".txt",
    }
    ext = next((e for k, e in ext_map.items() if k in ctype), "")

    # Fallback
    return f"file-{uuid.uuid4().hex}{ext or ''}", ext or ""


def _download_binary(url: str, timeout: int = 30) -> Tuple[bytes, str]:
    norm = _normalize_drive_link(url)
    r = requests.get(norm, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    content = r.content
    fname, ext = _guess_filename_and_ext(norm, r)
    # Small sanity
    if not content or len(content) < 50:  # avoid saving 0/very tiny bytes as resume
        raise ValueError("Downloaded content appears empty.")
    return content, (fname or f"file-{uuid.uuid4().hex}{ext}")


# ---------------------------
# Public API
# ---------------------------
def save_candidate_resume(
    client_name: str, client_id: int,
    job_title: str, job_id: int,
    candidate_id: int,
    resume_url: str
) -> Path:
    """
    Download a resume from a URL/Drive link and save it under:
    storage/clients/<clientId-clientSlug>/<jobId-jobSlug>/candidates/<candidateId>/resume.<ext>
    Returns the saved file path.
    """
    folder = _candidate_folder(client_name, client_id, job_title, job_id, candidate_id)
    # Download
    data, suggested_name = _download_binary(resume_url)

    # Normalize filename -> 'resume<ext>'
    ext = Path(suggested_name).suffix or ""
    target = folder / f"resume{ext}"
    # If already exists, keep a copy with suffix to avoid overwrite
    if target.exists():
        target = folder / f"resume-{uuid.uuid4().hex[:6]}{ext}"

    with open(target, "wb") as f:
        f.write(data)

    # Also keep a copy under a canonical name (latest)
    canonical = folder / "resume-latest" / f"resume{ext}"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    # copy without raising if same path
    if target.resolve() != canonical.resolve():
        shutil.copy2(target, canonical)

    return target


def save_candidate_metadata(
    client_name: str, client_id: int,
    job_title: str, job_id: int,
    candidate_id: int,
    metadata: dict
) -> Path:
    """
    Save candidate metadata JSON next to the resume:
    storage/clients/<clientId-clientSlug>/<jobId-jobSlug>/candidates/<candidateId>/metadata.json
    Returns the saved file path.
    """
    folder = _candidate_folder(client_name, client_id, job_title, job_id, candidate_id)
    meta_path = folder / "metadata.json"

    # enrich a bit
    payload = dict(metadata or {})
    payload["saved_at"] = datetime.utcnow().isoformat() + "Z"
    payload["client_id"] = client_id
    payload["job_id"] = job_id
    payload["candidate_id"] = candidate_id

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return meta_path
