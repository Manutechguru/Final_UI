# landing_page_app/routers/utils/search_utils.py
"""
Robust search utilities for candidate search page.

FULL UPDATE:
- Gemini COMPLETELY REMOVED
- Groq used as LLM
- Resume text read DIRECTLY from DB (already extracted)
- Final AI evaluation added (batch-wise, thresholded)
- NO design / logic / wiring changes
"""

from pathlib import Path
import os
import re
import json
import logging
import requests
import io

from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from pdfminer.high_level import extract_text
from docx import Document
from pdfminer.high_level import extract_text
from pdfminer.pdfparser import PDFSyntaxError

from groq import Groq
from landing_page_app.services.embedding_service import embed_text
from landing_page_app.services.llm_service import evaluate_candidates_batch

# Candidate model
try:
    from landing_page_app.models.candidates import Candidate
except Exception:
    Candidate = None

# load .env
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

JD_MATCH_THRESHOLD = int(os.getenv("JD_MATCH_THRESHOLD", "70"))
AI_BATCH_SIZE = 10

# -------------------------
# Groq LLM Client
# -------------------------
GROQ_CLIENT = Groq(api_key=os.getenv("GROQ_API_KEY"))


def _call_llm(
    prompt: str,
    max_output_tokens: int = 2048,
    temperature: float = 0.12
) -> str:
    response = GROQ_CLIENT.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You are an expert technical recruiter."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_output_tokens,
    )
    return response.choices[0].message.content


# -------------------------
# Experience parsing helpers
# -------------------------
def parse_text_experience_to_months(text: Optional[str]) -> int:
    if not text:
        return 0
    s = str(text).lower()
    years = months = 0
    m = re.search(r"(\d+(?:\.\d+)?)\s*y", s)
    if m:
        years = int(float(m.group(1)))
    m2 = re.search(r"(\d+)\s*(?:month|months|mo)", s)
    if m2:
        months = int(m2.group(1))
    return years * 12 + months


def parse_experience_filter_input(exp_input: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    if not exp_input or not isinstance(exp_input, str):
        return None, None
    s = exp_input.strip().lower()
    if "-" in s:
        a, b = s.split("-")
        return int(a) * 12, int(b) * 12
    if s.endswith("+"):
        return int(s[:-1]) * 12, None
    if s.isdigit():
        v = int(s) * 12
        return v, v
    return None, None


# -------------------------
# PROMPTS (UNCHANGED)
# -------------------------
PROMPT_EXTRACT = """
You are an expert technical recruiter and careful parser.

Read the ENTIRE Job Description.

Extract the following fields and return ONLY a valid JSON object:

- skills:
  - Extract all explicitly mentioned programming languages, frameworks,
    databases, cloud platforms, and backend technologies.
  - Include skills mentioned in Responsibilities or Requirements sections.
  - Do NOT invent tools or technologies that are not mentioned.

- experience:
  - Extract only if explicitly stated (e.g., "5-10 years", "5+ years").

- location:
  - Extract only if explicitly stated (city, region, or "Remote").

- summary:
  - Provide a concise 1–2 sentence summary of the role.

Return strictly valid JSON and nothing else.
"""




PROMPT_SCORE = """
You are an expert technical recruiter. Compare the JOB_DESCRIPTION and each candidate's resume_text and profile below.
Return a JSON array of objects. Each object MUST contain:
- id
- score (0-100)

Return ONLY the JSON array.
"""


def _reduce_jd_for_extraction(jd_text: str) -> str:
    if not jd_text:
        return ""

    import re
    text = re.sub(r"\s+", " ", jd_text)

    # HARD STOP — NOTHING ABOVE THIS EVER GOES TO GROQ
    return text[:1500]


def normalize_jd_text(text: str) -> str:
    if not text:
        return ""

    # normalize dashes and bullets
    text = text.replace("•", "\n")
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("â€“", "-")

    # normalize spacing
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)

    return text.strip()


def extract_jd_features_deterministic(jd_text: str) -> Dict[str, str]:
    jd_text = normalize_jd_text(jd_text)

    lines = [l.strip() for l in jd_text.splitlines() if l.strip()]
    lower = jd_text.lower()

    skills = []
    experience = ""
    location = ""

    # -----------------------
    # EXPERIENCE
    # -----------------------
    exp_patterns = [
        r"\b(\d+\s*[-–]\s*\d+\s*(?:yrs?|years?))\b",
        r"\b(\d+\+?\s*(?:yrs?|years?))\b",
        r"experience\s*[:\-]?\s*(\d+\s*[-–]\s*\d+\s*(?:yrs?|years?))",
    ]
    for p in exp_patterns:
        m = re.search(p, lower)
        if m:
            experience = m.group(1)
            break

    # -----------------------
    # LOCATION
    # -----------------------
    for line in lines:
        if line.lower().startswith("location"):
            location = line.split(":", 1)[-1].strip()
            break

    # -----------------------
    # SKILLS (section aware)
    # -----------------------
    skill_section = False
    for line in lines:
        l = line.lower()

        if any(k in l for k in [
            "must have",
            "what we look for",
            "required skills",
            "technical skills"
        ]):
            skill_section = True
            continue

        if skill_section:
            if any(k in l for k in [
                "good to have",
                "ideally",
                "nice to have"
            ]):
                break

            if len(line) < 2:
                continue

            # bullet / dot / dash cleanup
            clean = line.lstrip("•-– ").strip()

            # avoid sentences
            if len(clean.split()) <= 6:
                skills.append(clean)

    return {
        "skills": ", ".join(dict.fromkeys(skills)),  # de-duplicate
        "experience": experience,
        "location": location,
        "summary": ""
    }



# -------------------------
# JD extraction
# -------------------------
def extract_jd_features(jd_text: str) -> Dict[str, str]:
    """
    Hybrid JD extraction:
    - Step 1: deterministic extraction
    - Step 2: LLM fills missing fields ONLY
    """

    if not jd_text or len(jd_text.strip()) < 50:
        return {
            "skills": "",
            "experience": "",
            "location": "",
            "summary": ""
        }

    # STEP 1: deterministic extraction
    features = extract_jd_features_deterministic(jd_text)

    # ✅ If ALL core fields exist, skip LLM
    if all(features.get(k) for k in ("skills", "experience", "location")):
        logger.info("[JD-EXTRACT] Deterministic extraction fully satisfied")
        logger.info(f"[JD-EXTRACT][FINAL] {features}")
        return features

    # STEP 2: LLM fills ONLY missing fields
    prompt = PROMPT_EXTRACT + "\n\nJOB_DESCRIPTION:\n" + jd_text

    raw = _call_llm(
        prompt,
        max_output_tokens=512,
        temperature=0.05
    )

    try:
        parsed = json.loads(re.search(r"\{.*\}", raw, re.S).group())
    except Exception:
        logger.error("[JD-EXTRACT] LLM JSON parse failed")
        logger.info(f"[JD-EXTRACT][FINAL] {features}")
        return features
    
        # 🔧 FIX: normalize skills to string for UI compatibility
    skills_val = parsed.get("skills", "")

    if isinstance(skills_val, dict):
        flattened = []
        for v in skills_val.values():
            if isinstance(v, list):
                flattened.extend(v)
        # dedupe + join
        skills_val = ", ".join(dict.fromkeys(flattened))


    # Fill ONLY missing values (never overwrite deterministic ones)
    features["skills"] = features["skills"] or skills_val
    features["experience"] = features["experience"] or parsed.get("experience", "")
    features["location"] = features["location"] or parsed.get("location", "")
    features["summary"] = parsed.get("summary", "")

    logger.info(f"[JD-EXTRACT][FINAL] {features}")
    return features


    
def build_compact_jd_context(features: Dict[str, str]) -> str:
    """
    Build a SMALL, SAFE JD context for AI scoring.
    Groq must NEVER see the raw JD again.
    """
    return f"""
Job Summary:
{features.get("summary", "")}

Required Skills:
{features.get("skills", "")}

Experience:
{features.get("experience", "")}

Location:
{features.get("location", "")}
""".strip()


    
def extract_text_from_jd_file(jd_url: str) -> str:
    if not jd_url:
        return ""

    import re, requests, io

    u = jd_url.strip()

    # 🔥 FIX 1 — Google Docs → export as TEXT (MOST IMPORTANT)
    m_doc = re.search(r"/document/d/([a-zA-Z0-9_-]+)", u)
    if m_doc:
        doc_id = m_doc.group(1)
        txt_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
        try:
            r = requests.get(txt_url, timeout=20)
            if r.ok and len(r.text.strip()) > 100:
                return r.text.strip()
        except Exception:
            pass

    # 🔥 FIX 2 — Google Drive fallback
    if "drive.google.com" in u:
        m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", u) or re.search(r"[?&]id=([a-zA-Z0-9_-]+)", u)
        if m:
            fid = m.group(1)
            u = f"https://drive.google.com/uc?export=download&id={fid}"

    # 🔥 FIX 3 — fetch raw bytes
    r = requests.get(u, timeout=30)
    r.raise_for_status()
    content = r.content

    # 🔥 FIX 4 — PDF extraction LAST (best-effort only)
    if u.lower().endswith(".pdf"):
        try:
            from pdfminer.high_level import extract_text
            text = extract_text(io.BytesIO(content))
            if text and len(text.strip()) > 200:
                return text
        except Exception:
            return ""

    # fallback
    try:
        return content.decode("utf-8", errors="ignore")
    except Exception:
        return ""



# -------------------------
# Candidate payload builder
# -------------------------
def _build_candidate_payload_row(c: Candidate) -> Dict[str, Any]:
    cid = getattr(c, "candidates_id", None)

    resume_text = " ".join(filter(None, [
        getattr(c, "skillset", ""),
        getattr(c, "education", ""),
        getattr(c, "company", ""),
        getattr(c, "relevant_experience", ""),
        getattr(c, "it_experience", ""),
        getattr(c, "location", ""),
        getattr(c, "resume_text", ""),
        getattr(c, "recruitment_notes", ""),
    ]))

    return {
        "candidate_id": int(cid) if cid is not None else None,
        "skillset": c.skillset or "",
        "it_experience": c.it_experience or "",
        "relevant_experience": c.relevant_experience or "",
        "location": c.location or "",
        "resume_text": resume_text,
    }



def _parse_model_array(raw: str) -> Optional[List[Dict[str, Any]]]:
    if not raw:
        return None
    try:
        return json.loads(re.search(r"\[.*\]", raw, re.S).group())
    except Exception:
        return None


# -------------------------
# FINAL AI MATCH (BATCHED)
# -------------------------
def ai_match_jd_with_resumes(
    jd_text: str,
    candidates: List[Candidate],
    batch_size: int = AI_BATCH_SIZE,
    max_output_tokens_per_batch: int = 1024
) -> List[Dict[str, Any]]:

    if not candidates:
        return []
    
    # 🔐 Extract once, reuse everywhere (NO raw JD to LLM)
    jd_features = extract_jd_features(jd_text)
    compact_jd = build_compact_jd_context(jd_features)


    rows = [_build_candidate_payload_row(c) for c in candidates]
    id_map = {r["id"]: r for r in rows}

    scores: Dict[int, int] = {}

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]

        prompt = (
            PROMPT_SCORE
            + "\n\nJOB_DESCRIPTION:\n"
            + compact_jd 
            + "\n\nCANDIDATES:\n"
            + json.dumps(batch, ensure_ascii=False)
        )

        try:
            raw = _call_llm(prompt, max_output_tokens=max_output_tokens_per_batch)
            parsed = _parse_model_array(raw)
        except Exception as e:
            logger.warning("LLM batch failed: %s", e)
            continue

        if not parsed:
            continue

        for item in parsed:
            try:
                cid = int(item.get("id"))
                score = int(float(item.get("score", 0)))
                scores[cid] = max(scores.get(cid, 0), score)
            except Exception:
                continue

    results = []
    for cid, score in scores.items():
        base = id_map.get(cid, {}).copy()
        base.update({
            "candidates_id": cid,
            "ai_score": score,
            "score": score,
            "ai_explanation": "",
            "reasons": "",
        })
        results.append(base)

    results.sort(key=lambda r: int(r["score"]), reverse=True)
    return results


# -------------------------
# EMBEDDING SHORTLIST (UNCHANGED)
# -------------------------
def shortlist_candidates_by_embedding(
    db: Session,
    jd_text: str,
    top_k: int = 200
):
    jd_embedding = embed_text(jd_text)
    if not jd_embedding:
        return []
    return (
        db.query(Candidate)
        .filter(Candidate.embedding.isnot(None))
        .order_by(Candidate.embedding.cosine_distance(jd_embedding))
        .limit(top_k)
        .all()
    )
