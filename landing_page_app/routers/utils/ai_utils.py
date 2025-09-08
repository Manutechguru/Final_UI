
import os, io, re, json, requests
from typing import Dict, Any, Optional, Tuple, List

# optional: load dotenv if present so .env keys work automatically
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# optional storage util from your repo (preferred for Drive links)
try:
    from landing_page_app.routers.utils.storage_utils import _download_binary
except Exception:
    _download_binary = None

# ---- Config ----
def _normalize_model_name(name: Optional[str]) -> str:
    if not name:
        return "gemini-1.5-flash"
    n = name.strip().lower()
    mapping = {
        "flash-1.5": "gemini-1.5-flash",
        "1.5-flash": "gemini-1.5-flash",
        "pro-1.5": "gemini-1.5-pro",
        "1.5-pro": "gemini-1.5-pro",
    }
    return mapping.get(n, name)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = _normalize_model_name(os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CandidateScorer/1.0; +https://example.local)"
}


# ---- File decoding helpers ----
def _bytes_to_text(data: bytes, name: str = "", content_type: str = "") -> str:
    name_l = (name or "").lower()
    ctype = (content_type or "").lower()
    try:
        if data[:4] == b"%PDF" or name_l.endswith(".pdf") or "pdf" in ctype:
            # Prefer PyPDF2; fall back gracefully if not available
            try:
                from PyPDF2 import PdfReader
                rdr = PdfReader(io.BytesIO(data))
                return "\n".join((p.extract_text() or "") for p in getattr(rdr, "pages", []))
            except Exception:
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(stream=data, filetype="pdf")
                    text = []
                    for page in doc:
                        text.append(page.get_text())
                    return "\n".join(text)
                except Exception:
                    return data.decode("utf-8", "ignore")
        if name_l.endswith(".docx") or "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in ctype:
            try:
                from docx import Document
                doc = Document(io.BytesIO(data))
                return "\n".join(p.text for p in doc.paragraphs)
            except Exception:
                return data.decode("utf-8", "ignore")
        if name_l.endswith(".rtf") or "rtf" in ctype:
            txt = data.decode("utf-8", "ignore")
            # quick-n-dirty RTF to text
            txt = re.sub(r"\\'..", "", txt)  # remove escaped bytes
            txt = re.sub(r"\\[a-z]+\d*", "", txt)  # control words
            txt = re.sub(r"[{}]", " ", txt)
            return re.sub(r"\s+", " ", txt)
        # Default: try text/HTML and strip tags
        text = data.decode("utf-8", "ignore")
        if "<html" in text.lower():
            text = re.sub(r"<\s*script[^>]*>.*?<\s*/\s*script>", " ", text, flags=re.I|re.S)
            text = re.sub(r"<\s*style[^>]*>.*?<\s*/\s*style>", " ", text, flags=re.I|re.S)
            text = re.sub(r"<[^>]+>", " ", text)
        return text
    except Exception:
        return ""


# ---- HTTP helpers ----
def _http_fetch(url: str, timeout: int = 30) -> Tuple[bytes, str, str]:
    r = requests.get(url, timeout=timeout, allow_redirects=True, headers=DEFAULT_HEADERS)
    r.raise_for_status()
    name = ""
    cd = r.headers.get("Content-Disposition", "") or ""
    m = re.search(r"filename\*=.*?''(.+)|filename=\"?([^\";]+)\"?", cd)
    if m:
        name = m.group(1) or m.group(2) or ""
    if not name:
        name = url.split("/")[-1].split("?")[0]
    return r.content, name, r.headers.get("Content-Type","")


def _drive_id_from_url(url: str) -> Optional[str]:
    # Supports: /file/d/<id>/, open?id=<id>, uc?id=<id>
    m = re.search(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?id=)([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    # Also support docs viewer links: https://drive.google.com/uc?id=<id>&export=download
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else None


def _dropbox_direct(url: str) -> Optional[str]:
    # convert ?dl=0 to raw file
    if "dropbox.com" in url:
        if "dl=0" in url:
            return url.replace("dl=0", "dl=1")
        if not re.search(r"[?&]dl=1", url):
            # force download param
            return url + ("&" if "?" in url else "?") + "dl=1"
    return None


def _onedrive_direct(url: str) -> Optional[str]:
    # Heuristic: force download=1 if possible
    if "1drv.ms" in url or "sharepoint.com" in url or "onedrive.live.com" in url:
        if "download=1" not in url:
            return url + ("&" if "?" in url else "?") + "download=1"
    return None


def fetch_text_from_link(url: str, timeout: int = 30) -> str:
    if not url:
        return ""
    url = url.strip()

    # Google Docs (native doc) export to plain text
    m_doc = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9\-_]+)", url)
    if m_doc:
        doc_id = m_doc.group(1)
        try:
            r = requests.get(f"https://docs.google.com/document/d/{doc_id}/export?format=txt", timeout=timeout, headers=DEFAULT_HEADERS)
            r.raise_for_status()
            return r.text
        except Exception:
            pass

    # Google Drive file (PDF/DOCX/etc.) -> force download
    gid = _drive_id_from_url(url)
    if gid:
        for candidate in [
            f"https://drive.google.com/uc?export=download&id={gid}",
            f"https://drive.usercontent.google.com/download?id={gid}&export=download"
        ]:
            try:
                data, name, ctype = _http_fetch(candidate, timeout=timeout)
                if data and len(data) > 0 and b"Google Drive - Virus scan warning" not in data:
                    return _bytes_to_text(data, name, ctype)
            except Exception:
                continue

    # Dropbox direct
    dbx = _dropbox_direct(url)
    if dbx:
        try:
            data, name, ctype = _http_fetch(dbx, timeout=timeout)
            return _bytes_to_text(data, name, ctype)
        except Exception:
            pass

    # OneDrive/SharePoint best-effort
    od = _onedrive_direct(url)
    if od:
        try:
            data, name, ctype = _http_fetch(od, timeout=timeout)
            return _bytes_to_text(data, name, ctype)
        except Exception:
            pass

    # Prefer your storage util (handles Drive/Google auth) if present
    if _download_binary:
        try:
            data, name = _download_binary(url, timeout=timeout)
            if isinstance(data, bytes):
                return _bytes_to_text(data, name)
            if isinstance(data, str):
                return data
        except Exception:
            pass

    # Fallback to raw HTTP
    try:
        data, name, ctype = _http_fetch(url, timeout=timeout)
        text = _bytes_to_text(data, name, ctype)
        # heuristics: ignore typical "permission denied" HTML pages
        if "need permission" in text.lower() and "google" in text.lower():
            return ""
        return text
    except Exception:
        return ""


def _truncate(text: str, limit: int = 12000) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: int(limit * 0.6)] + "\n\n... (truncated) ...\n\n" + text[-int(limit * 0.4):]


def _build_prompt(resume: str, jd: str, cand_name: str = "", job_title: str = "") -> str:
    # When response_schema is supported, model will return strict JSON,
    # but we keep the instruction for older models for extra robustness.
    return (
        "You are an expert technical recruiter. Compare the JOB DESCRIPTION to the CANDIDATE RESUME and produce ONLY valid JSON with two fields:\n"
        '{"score": <integer 0-100>, "summary": "<a concise comparison text (may include bullets/newlines)>"}\n\n'
        "The summary must include (briefly):\n"
        "- Top strengths (up to 3 bullet points)\n"
        "- Top gaps (up to 3 bullet points)\n"
        "- Skill-match percentage (approx.)\n"
        "- Experience match (years vs what the JD expects)\n"
        "- One-line verdict (hire / maybe / not-fit)\n\n"
        f"Job Title: {job_title}\n\nJOB DESCRIPTION:\n{_truncate(jd)}\n\n"
        f"Candidate Name: {cand_name}\n\nRESUME TEXT:\n{_truncate(resume)}\n\n"
        "Return EXACTLY a JSON object and NOTHING ELSE. Score must be integer 0-100."
    )


def _heuristic(candidate: Dict[str, Any], jd_text: str) -> Dict[str, Any]:
    skills_raw = candidate.get("skillset") or ""
    if isinstance(skills_raw, str):
        # allow pipe/comma/semicolon separated
        parts = re.split(r"[|,;/]\s*", skills_raw)
    elif isinstance(skills_raw, list):
        parts = [str(x) for x in skills_raw]
    else:
        parts = [str(skills_raw)]
    skills = [s.strip().lower() for s in parts if s and s.strip()]
    jd_lower = (jd_text or "").lower()
    matched = [s for s in skills if s and s in jd_lower]
    skill_pct = int((len(matched)/max(1,len(skills)))*100)
    yrs = 0.0
    try:
        m = re.findall(r"\d+(?:\.\d+)?", str(candidate.get("relevant_exp") or candidate.get("it_experience") or ""))
        yrs = float(m[0]) if m else 0.0
    except Exception:
        yrs = 0.0
    score = int(max(0, min(100, skill_pct*0.7 + min(20, yrs*3))))
    summary = (
        f"- Strengths: {', '.join(matched[:3]) or 'None'}\n"
        f"- Gaps: (automatic) check JD for missing keywords\n"
        f"- Skill-match: ~{skill_pct}%\n"
        f"- Experience: ~{yrs} yrs\n"
        f"- Verdict: {'Good fit' if score>=75 else 'Maybe' if score>=45 else 'Not a fit'}"
    )
    return {"score": score, "summary": summary}


def score_candidate(candidate: Dict[str, Any], jd_text: Optional[str] = None, jd_link: Optional[str] = None) -> Dict[str, Any]:
    """
    Reads resume & JD (from direct text or links), calls Gemini, and returns {score, summary}.
    If API key is missing or call fails, falls back to a transparent heuristic based on skills/years.
    """
    # ---- Gather resume text ----
    resume_text = candidate.get("resume_text") or ""
    resume_url: Optional[str] = None
    for key in ("resume","resume_url","resumelinks","resume_link"):
        if not resume_url and candidate.get(key):
            resume_url = candidate.get(key)
    # support multiple links separated by space/comma
    if not resume_text and resume_url:
        links: List[str] = re.split(r"[\s,]+", str(resume_url).strip())
        blob = []
        for link in links:
            t = fetch_text_from_link(link)
            if t:
                blob.append(t)
        resume_text = "\n\n".join(blob)

    # ---- Gather JD text ----
    jd_full = (jd_text or "") or ""
    if (not jd_full or len(str(jd_full).strip()) < 80) and jd_link:
        jd_full = fetch_text_from_link(jd_link)

    # ---- If nothing to compare, bail out quickly ----
    if not resume_text and not jd_full:
        return _heuristic(candidate, "")

    # ---- If no API key, use heuristic ----
    if not GEMINI_API_KEY:
        return _heuristic(candidate, jd_full)

    # ---- Build prompt and call Gemini ----
    prompt = _build_prompt(resume_text or "", jd_full or "", candidate.get("candidate_name",""), candidate.get("job_title",""))
    payload = {
        "contents":[{"parts":[{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 768,
            # Ask for strict JSON if supported by the model endpoint
            "response_mime_type": "application/json",
            "response_schema": {
                "type": "OBJECT",
                "properties": {
                    "score": {"type": "INTEGER"},
                    "summary": {"type": "STRING"}
                },
                "required": ["score","summary"]
            }
        }
    }
    try:
        resp = requests.post(GEMINI_API_URL, params={"key":GEMINI_API_KEY}, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        text = (data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "") or "")
        # attempt strict JSON parse, else extract first JSON object substring
        obj = None
        try:
            obj = json.loads(text)
        except Exception:
            m = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if m:
                try:
                    obj = json.loads(m.group(0))
                except Exception:
                    obj = None
        if isinstance(obj, dict):
            try:
                score = int(obj.get("score", 0))
            except Exception:
                score = 0
            score = max(0, min(100, score))
            summary = str(obj.get("summary", "")).strip() or "No explanation provided."
            return {"score": score, "summary": summary}
        # if parse failed, fallback to regex extraction for score & plain text summary
        score = 0
        mscore = re.search(r'"score"\s*:\s*(\d+)', text)
        if mscore:
            score = int(mscore.group(1))
        # summary fallback: try "summary" field substring or use full text
        msum = re.search(r'"summary"\s*:\s*"([^"]+)"', text, flags=re.DOTALL)
        summary = msum.group(1) if msum else text.strip()
        if not summary:
            return _heuristic(candidate, jd_full)
        return {"score": max(0,min(100,int(score))), "summary": summary}
    except Exception:
        # network or parsing error -> heuristic fallback
        return _heuristic(candidate, jd_full)
