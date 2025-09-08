# landing_page_app/routers/utils/search_utils.py
"""
Robust search utilities for candidate search page.

Exports:
- parse_experience_filter_input
- parse_text_experience_to_months
- fetch_text_from_url
- extract_jd_features
- ai_match_jd_with_resumes

Designed to be a drop-in replacement. Keeps function names/signatures used across the app.
"""

from pathlib import Path
import os
import re
import json
import logging
import io
import time
from typing import List, Optional, Tuple, Dict, Any
from threading import Lock

# try to import Candidate model if present (used for shim in fallbacks)
try:
    from landing_page_app.models.candidates import Candidate
except Exception:
    Candidate = None

# load .env if dotenv available (helps local dev)
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()
except Exception:
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------
# API keys / Gemini config
# -------------------------
def _collect_api_keys() -> List[str]:
    keys = []
    raw = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_KEYS", "")
    if raw:
        parts = re.split(r"[,\n\r]+", raw)
        for p in parts:
            if p and p.strip():
                keys.append(p.strip())
    # numbered keys
    for i in range(1, 21):
        v = os.getenv(f"GEMINI_API_KEY_{i}")
        if v and v.strip():
            keys.append(v.strip())
    # single-key fallbacks
    single = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if single and single.strip():
        keys.append(single.strip())
    # dedupe preserving order
    seen = set()
    out = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out

API_KEYS: List[str] = _collect_api_keys()
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL", os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash"))
JD_MATCH_THRESHOLD = int(os.getenv("JD_MATCH_THRESHOLD", "70"))
GEMINI_PER_KEY_RETRIES = int(os.getenv("GEMINI_PER_KEY_RETRIES", "2"))
GEMINI_DEBUG = os.getenv("GEMINI_DEBUG", "0").lower() in ("1","true","yes")

logger.info(f"search_utils: loaded {len(API_KEYS)} Gemini key(s); model='{GEMINI_MODEL_NAME}'; threshold={JD_MATCH_THRESHOLD}")

# optional libs
_requests_available = False
_pypdf2_available = False
_docx_available = False
_try_pdfminer = False
try:
    import requests
    _requests_available = True
except Exception:
    requests = None
    logger.debug("requests not available")

try:
    import PyPDF2
    _pypdf2_available = True
except Exception:
    PyPDF2 = None

try:
    import docx  # python-docx
    _docx_available = True
except Exception:
    docx = None

try:
    import pdfminer
    _try_pdfminer = True
except Exception:
    pdfminer = None

# generative ai SDK
try:
    import google.generativeai as genai  # type: ignore
except Exception:
    genai = None
    logger.warning("google.generativeai not importable. AI features disabled or limited.")

_rotation_lock = Lock()
_rotation_index = 0

# -------------------------
# Experience parsing helpers
# -------------------------
def parse_text_experience_to_months(text: Optional[str]) -> int:
    if not text:
        return 0
    s = str(text).lower()
    years = months = 0
    m = re.search(r"(\d+(?:\.\d+)?)\s*y(?:ears?)?\b", s)
    if m:
        try:
            years = int(float(m.group(1)))
        except Exception:
            try:
                years = int(float(float(m.group(1))))
            except Exception:
                years = 0
    m2 = re.search(r"(\d+)\s*(?:month|months|mo)\b", s)
    if m2:
        try:
            months = int(m2.group(1))
        except Exception:
            months = 0
    # support "4.5 years" approx
    m_float = re.search(r"(\d+(?:\.\d+)?)\s*years?", s)
    if m_float and not m:
        try:
            years = int(float(m_float.group(1)))
        except Exception:
            pass
    return years * 12 + months

def parse_experience_filter_input(exp_input: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    if not exp_input or not isinstance(exp_input, str):
        return None, None
    s = exp_input.strip().lower()
    m_range = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", s)
    if m_range:
        try:
            a = int(m_range.group(1)); b = int(m_range.group(2))
            return a * 12, b * 12
        except Exception:
            return None, None
    m_plus = re.match(r"^(\d+)\s*\+$", s)
    if m_plus:
        try:
            a = int(m_plus.group(1))
            return a * 12, None
        except Exception:
            return None, None
    m_single = re.match(r"^(\d+)$", s)
    if m_single:
        try:
            a = int(m_single.group(1))
            return a * 12, a * 12
        except Exception:
            return None, None
    m_yd = re.search(r"(\d+)\s*y", s)
    if m_yd:
        try:
            a = int(m_yd.group(1)); return a * 12, a * 12
        except Exception:
            return None, None
    return None, None

# -------------------------
# Text extraction from files / urls
# -------------------------
def _clean_text_whitespace(s: Optional[str], max_len: int = 300000) -> str:
    if not s:
        return ""
    txt = re.sub(r"\s+", " ", str(s)).strip()
    if len(txt) > max_len:
        return txt[:max_len] + " ..."
    return txt

def _extract_text_from_pdf_bytes(b: bytes) -> str:
    if not b:
        return ""
    if _pypdf2_available:
        try:
            reader = PyPDF2.PdfReader(io.BytesIO(b))
            pages = []
            for p in reader.pages:
                try:
                    pages.append(p.extract_text() or "")
                except Exception:
                    pages.append("")
            return _clean_text_whitespace(" ".join(pages))
        except Exception:
            pass
    if _try_pdfminer:
        try:
            from io import BytesIO
            from pdfminer.high_level import extract_text
            return _clean_text_whitespace(extract_text(BytesIO(b)))
        except Exception:
            pass
    try:
        return _clean_text_whitespace(b.decode("utf-8", errors="ignore"))
    except Exception:
        return ""

def _extract_text_from_docx_bytes(b: bytes) -> str:
    if not b:
        return ""
    if _docx_available:
        try:
            d = docx.Document(io.BytesIO(b))
            paragraphs = [p.text for p in d.paragraphs if p.text]
            return _clean_text_whitespace(" ".join(paragraphs))
        except Exception:
            pass
    try:
        return _clean_text_whitespace(b.decode("utf-8", errors="ignore"))
    except Exception:
        return ""

def fetch_text_from_url(url: Optional[str], timeout: int = 12) -> str:
    """
    Best-effort fetch of text from URL. Handles Google Docs/Drive, PDF, DOCX, HTML/text.
    Returns cleaned text or empty string on failure.
    """
    if not url:
        return ""
    u = url.strip()
    lower_u = u.lower()

    if any(x in lower_u for x in ("resume.link", "example.com", "placeholder", "dummy")):
        logger.debug("fetch_text_from_url: skipping placeholder link %s", u)
        return ""

    # Google Docs -> export as txt
    m_doc = re.search(r"/document/d/([a-zA-Z0-9_-]+)", u)
    if m_doc:
        doc_id = m_doc.group(1)
        u = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"

    # drive links -> download endpoint
    if "drive.google.com" in u:
        m1 = re.search(r"/file/d/([a-zA-Z0-9_-]+)", u)
        if m1:
            fid = m1.group(1)
            u = f"https://drive.google.com/uc?export=download&id={fid}"
        else:
            m2 = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", u)
            if m2:
                fid = m2.group(1)
                u = f"https://drive.google.com/uc?export=download&id={fid}"

    if not _requests_available:
        logger.warning("fetch_text_from_url: requests not installed; cannot fetch remote URL.")
        return ""

    try:
        resp = requests.get(u, timeout=timeout)
        resp.raise_for_status()
    except Exception as e:
        logger.debug("fetch_text_from_url: failed to fetch %s: %s", u, e)
        return ""

    ctype = (resp.headers.get("content-type") or "").lower()
    if "pdf" in ctype or u.lower().endswith(".pdf"):
        return _extract_text_from_pdf_bytes(resp.content)
    if "officedocument" in ctype or "msword" in ctype or u.lower().endswith(".docx"):
        return _extract_text_from_docx_bytes(resp.content)
    if "text" in ctype or "html" in ctype or u.lower().endswith((".txt", ".html", ".htm")):
        try:
            txt = resp.text
            if "<html" in txt.lower():
                txt = re.sub(r"<script.*?</script>", "", txt, flags=re.S | re.I)
                txt = re.sub(r"<style.*?</style>", "", txt, flags=re.S | re.I)
                txt = re.sub(r"<[^>]+>", " ", txt)
            return _clean_text_whitespace(txt)
        except Exception:
            return _clean_text_whitespace(resp.content.decode("utf-8", errors="ignore"))

    # fallback pdf/docx heuristics
    txt_pdf = _extract_text_from_pdf_bytes(resp.content)
    if txt_pdf:
        return txt_pdf
    txt_docx = _extract_text_from_docx_bytes(resp.content)
    if txt_docx:
        return txt_docx
    try:
        return _clean_text_whitespace(resp.content.decode("utf-8", errors="ignore"))
    except Exception:
        return ""

# -------------------------
# Gemini calling with rotation & retry
# -------------------------
def _extract_text_from_response(resp) -> str:
    try:
        if hasattr(resp, "text") and resp.text:
            return resp.text
        if hasattr(resp, "output") and resp.output:
            out = resp.output
            if isinstance(out, (list, tuple)) and len(out) > 0:
                first = out[0]
                if hasattr(first, "text") and first.text:
                    return first.text
                if hasattr(first, "content") and first.content:
                    try:
                        return str(first.content)
                    except Exception:
                        return str(first)
            return str(out)
        if hasattr(resp, "candidates") and resp.candidates:
            c = resp.candidates[0]
            if hasattr(c, "content"):
                return str(c.content)
            if hasattr(c, "text"):
                return c.text
            return str(c)
        # dict-like
        if isinstance(resp, dict):
            # try deep extraction
            cands = resp.get("candidates", [])
            if cands:
                first = cands[0]
                # content.parts[0].text
                content = first.get("content", {})
                parts = content.get("parts", [])
                if parts and isinstance(parts, list):
                    p0 = parts[0]
                    if isinstance(p0, dict) and "text" in p0:
                        return p0["text"]
            return json.dumps(resp)
        return str(resp)
    except Exception:
        try:
            return str(resp)
        except Exception:
            return ""

def _call_gemini_with_rotation(prompt: str, max_output_tokens: int = 2048, temperature: float = 0.2,
                               per_key_attempts: int = 2, backoff_base: float = 0.8) -> str:
    global _rotation_index
    if not API_KEYS:
        raise RuntimeError("No GEMINI API keys configured.")
    if genai is None:
        raise RuntimeError("google.generativeai module not available.")

    n = len(API_KEYS)
    last_exc = None

    with _rotation_lock:
        start_idx = _rotation_index % n

    for attempt_idx in range(n):
        key_idx = (start_idx + attempt_idx) % n
        key = API_KEYS[key_idx]
        for try_num in range(per_key_attempts):
            try:
                try:
                    genai.configure(api_key=key)
                except Exception:
                    try:
                        setattr(genai, "api_key", key)
                    except Exception:
                        pass

                try:
                    if hasattr(genai, "GenerativeModel"):
                        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
                        resp = model.generate_content(
                            prompt,
                            generation_config={
                                "temperature": temperature,
                                "top_p": 0.9,
                                "max_output_tokens": max_output_tokens,
                            }
                        )
                        text = _extract_text_from_response(resp)
                        if text:
                            with _rotation_lock:
                                _rotation_index = (key_idx + 1) % n
                            logger.debug("Gemini success with key_idx=%d (GenerativeModel)", key_idx)
                            return text
                except Exception as e:
                    logger.debug("GenerativeModel failed for key %d: %s", key_idx, e)

                try:
                    if hasattr(genai, "generate_text"):
                        resp = genai.generate_text(model=GEMINI_MODEL_NAME, input=prompt, max_output_tokens=max_output_tokens)
                        text = _extract_text_from_response(resp)
                        if text:
                            with _rotation_lock:
                                _rotation_index = (key_idx + 1) % n
                            logger.debug("Gemini success with key_idx=%d (generate_text)", key_idx)
                            return text
                except Exception as e:
                    logger.debug("generate_text failed for key %d: %s", key_idx, e)

                raise RuntimeError(f"Gemini key index {key_idx} did not return readable text on try {try_num}")

            except Exception as e:
                last_exc = e
                logger.warning("Gemini key index %d failed (try %d): %s", key_idx, try_num, e)
                time.sleep(backoff_base * (1.5 ** try_num))
                continue

        logger.warning("Gemini key index %d failed after %d attempts; trying next key.", key_idx, per_key_attempts)

    raise RuntimeError(f"All Gemini API keys failed. Last error: {last_exc}")

# -------------------------
# JD extraction & scoring
# -------------------------
PROMPT_EXTRACT = """
You are an expert technical recruiter and a careful parser. Read the ENTIRE Job Description below.
Extract the primary REQUIRED items and output ONLY a single JSON object with keys:

- skills: a comma-separated string of the main required skills/technologies/frameworks/tools (e.g. "Python, Django, PostgreSQL, AWS Lambda").
- experience: a short canonical experience requirement in years using one of these formats: "X-Y" (range, years), "X+" (minimum), or a single "X".
- location: preferred location(s) as a short string (city, region, or "Remote" if remote). If none specified, return an empty string.
- summary: 1-2 sentence concise summary of the JD's focus.

Return strictly valid JSON object and nothing else.
"""

PROMPT_SCORE = """
You are an expert technical recruiter. Compare the JOB_DESCRIPTION and each candidate's resume_text and profile below.
Return a JSON array of objects. Each object must contain:
- id (integer): candidate id as provided,
- score (integer 0-100): how close the candidate is to the JD,
- reasons (short string): 1-2 short sentences explaining main reasons for the score.

Scoring guidance:
- Skills: 60% of score
- Experience: 25%
- Location: 15%
Output only a JSON array and nothing else.
"""

def extract_jd_features(jd_text: str) -> Dict[str, str]:
    if not jd_text:
        return {"skills": "", "experience": "", "location": "", "summary": ""}

    prompt = PROMPT_EXTRACT + "\n\nJOB_DESCRIPTION:\n" + jd_text
    try:
        raw = _call_gemini_with_rotation(prompt, max_output_tokens=512, temperature=0.12)
    except Exception as e:
        logger.error("extract_jd_features: model call failed: %s", e)
        return {"skills": "", "experience": "", "location": "", "summary": ""}

    parsed = None
    match = re.search(r"(\{(?:.|\s)*\})", raw, flags=re.S)
    if match:
        try:
            parsed = json.loads(match.group(1))
        except Exception:
            parsed = None
    if parsed is None:
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None

    if isinstance(parsed, dict):
        return {
            "skills": (parsed.get("skills") or "").strip(),
            "experience": (parsed.get("experience") or "").strip(),
            "location": (parsed.get("location") or "").strip(),
            "summary": (parsed.get("summary") or "").strip(),
        }
    logger.error("extract_jd_features: unable to parse JSON from model output")
    return {"skills": "", "experience": "", "location": "", "summary": ""}

def ai_match_jd_with_resumes(jd_text: str, candidates: List[object]) -> List[Dict[str, Any]]:
    if not candidates:
        return []

    payload = []
    id_to_row = {}
    for c in candidates:
        cid = getattr(c, "candidates_id", None) or getattr(c, "candidate_id", None)
        raw_links = getattr(c, "resumelinks", "") or ""
        resume_text = ""
        if raw_links and isinstance(raw_links, str):
            parts = [p.strip() for p in re.split(r"[\n,;]+", raw_links) if p.strip()]
            for link in parts:
                try:
                    t = fetch_text_from_url(link)
                    if t:
                        resume_text += " " + t
                except Exception as e:
                    logger.debug("ai_match_jd_with_resumes: fetch resume %s for %s failed: %s", link, cid, e)
        resume_text = _clean_text_whitespace(resume_text)
        row = {
            "id": int(cid) if cid is not None else None,
            "name": getattr(c, "candidate_name", "") or getattr(c, "name", "") or "",
            "email": getattr(c, "email", "") or "",
            "contact": getattr(c, "contact", "") or "",
            "location": getattr(c, "location", "") or "",
            "skillset": getattr(c, "skillset", "") or "",
            "it_experience": getattr(c, "it_experience", "") or getattr(c, "it_exp", "") or "",
            "relevant_experience": getattr(c, "relevant_experience", "") or "",
            "education": getattr(c, "education", "") or "",
            "company": getattr(c, "company", "") or "",
            "recruitment_notes": getattr(c, "recruitment_notes", "") or "",
            "resume_text": resume_text[:200000] if resume_text else "",
        }
        payload.append(row)
        id_to_row[row["id"]] = row

    prompt = PROMPT_SCORE + "\n\nJOB_DESCRIPTION:\n" + (jd_text or "") + "\n\nCANDIDATES:\n" + json.dumps(payload, ensure_ascii=False)

    try:
        raw = _call_gemini_with_rotation(prompt, max_output_tokens=4096, temperature=0.25)
    except Exception as e:
        logger.error("ai_match_jd_with_resumes: model call failed (all keys tried): %s", e)
        return []

    parsed = None
    match = re.search(r"(\[.*\])", raw, flags=re.S)
    if match:
        try:
            parsed = json.loads(match.group(1))
        except Exception:
            parsed = None
    if parsed is None:
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None

    if not isinstance(parsed, list):
        logger.error("ai_match_jd_with_resumes: model response not a JSON array")
        return []

    results = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        try:
            cid = int(item.get("id"))
        except Exception:
            continue
        try:
            score = int(float(item.get("score", 0)))
        except Exception:
            score = 0
        reasons = (item.get("reasons") or item.get("reason") or item.get("explanation") or "")[:2000]
        if score >= JD_MATCH_THRESHOLD:
            row = id_to_row.get(cid, {}).copy()
            row.update({"candidates_id": cid, "score": max(0, min(100, score)), "reasons": reasons})
            results.append(row)

    results.sort(key=lambda r: int(r.get("score", 0)), reverse=True)
    return results


# -------------------------
# Manual search helper: AI match using manual keywords
# -------------------------
def _build_pseudo_jd_from_keywords(skills: str, experience: str, location: str) -> str:
    s = (skills or "").strip()
    e = (experience or "").strip()
    l = (location or "").strip()
    parts = []
    if s:
        parts.append(f"Required Skills: {s}")
    if e:
        parts.append(f"Minimum Experience: {e}")
    if l:
        parts.append(f"Preferred Location: {l}")
    if not parts:
        return "General software/IT candidate search."
    return "\n".join(parts)


def ai_match_keywords_with_resumes(skills: str, experience: str, location: str, candidates: List[Dict[str, Any]]):
    """Thin wrapper that reuses ai_match_jd_with_resumes with a pseudo-JD built
    from the manual search keywords. Returns a list of dicts with candidate ids
    and AI scores/explanations, tolerant to schema differences.
    """
    jd_text = _build_pseudo_jd_from_keywords(skills, experience, location)
    raw = ai_match_jd_with_resumes(jd_text, candidates) or []
    out = []
    for row in raw:
        cid = row.get("candidate_id") or row.get("candidates_id") or row.get("id")
        score = row.get("ai_score") or row.get("score")
        expl = row.get("ai_explanation") or row.get("reasons") or row.get("explanation")
        out.append({
            "candidate_id": cid,
            "ai_score": score,
            "ai_explanation": expl,
        })
    return out
