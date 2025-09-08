from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional

from landing_page_app.database import get_db
from landing_page_app.models.candidates import Candidate
from landing_page_app.models.jobs import Job

# optional mapping model
try:
    from landing_page_app.models.candidate_status_history import CandidateJDMapping
except Exception:
    CandidateJDMapping = None

# ai util (fetches resume & JD, calls Gemini, returns {"score", "summary"})
try:
    from landing_page_app.routers.utils.ai_utils import score_candidate as ai_score
except Exception:
    from landing_page_app.utils.ai_utils import score_candidate as ai_score

router = APIRouter(prefix="/candidates", tags=["Candidate Scoring"])


def _get_obj_any(db, Model, checks: dict):
    for k, v in checks.items():
        if hasattr(Model, k):
            try:
                return db.query(Model).filter(getattr(Model, k) == v).first()
            except Exception:
                continue
    return None


def _get_candidate(db: Session, cid: int) -> Optional[Candidate]:
    return _get_obj_any(db, Candidate, {"candidates_id": cid, "candidate_id": cid, "id": cid})


def _get_job(db: Session, jid: int) -> Optional[Job]:
    return _get_obj_any(db, Job, {"job_id": jid, "id": jid})


def _mapping_row(db, cid: int, jid: int):
    if not CandidateJDMapping:
        return None
    for cfield in ("candidate_id", "candidates_id"):
        for jfield in ("jd_id", "job_id"):
            if hasattr(CandidateJDMapping, cfield) and hasattr(CandidateJDMapping, jfield):
                try:
                    row = db.query(CandidateJDMapping).filter(
                        getattr(CandidateJDMapping, cfield) == cid,
                        getattr(CandidateJDMapping, jfield) == jid
                    ).first()
                    if row:
                        return row
                except Exception:
                    continue
    return None


def _candidate_pk(candidate: Candidate) -> int:
    for a in ("candidates_id", "candidate_id", "id"):
        if hasattr(candidate, a):
            return int(getattr(candidate, a))
    raise ValueError("PK not found")


def _candidate_to_dict(cand: Candidate) -> dict:
    def g(*names, default=""):
        for n in names:
            if hasattr(cand, n):
                v = getattr(cand, n)
                if v is not None:
                    return v
        return default
    return {
        "candidate_name": g("name","candidate_name"),
        "email": g("email"),
        "skillset": g("skills","skillset"),
        "relevant_exp": g("relevant_experience","rel_exp"),
        "it_experience": g("it_experience","itexp"),
        "education": g("education"),
        "company": g("company"),
        "resume": g("resume","resumelinks","resume_url","resume_link"),
        "location": g("location","city"),
    }


def _job_text_and_link(job: Job):
    for a in ("job_description","job_desc","description","jd_text","job_text"):
        if hasattr(job, a) and getattr(job, a):
            return str(getattr(job, a)), None
    for a in ("jd_drive_link","drive_link","job_doc_link","job_link","jd_link","job_drive_link","drive_url"):
        if hasattr(job, a) and getattr(job, a):
            return "", str(getattr(job, a))
    return getattr(job, "job_title", "") or "", None


def _job_title(job: Job) -> str:
    for a in ("job_title","title","position","role"):
        if hasattr(job, a) and getattr(job, a):
            return str(getattr(job, a))
    return ""


def _store_score_only(db: Session, candidate: Candidate, jid: int, score: int):
    # try mapping
    mapping = _mapping_row(db, _candidate_pk(candidate), jid)
    if mapping:
        for a in ("ai_score","ai_score_value"):
            if hasattr(mapping, a):
                setattr(mapping, a, int(score))
                db.commit()
                return
    # fallback to candidate
    for a in ("ai_score","ai_score_value"):
        if hasattr(candidate, a):
            setattr(candidate, a, int(score))
            db.commit()
            return
    # nothing writable -> do nothing (non-fatal)


def _read_stored_score(db: Session, candidate: Candidate, jid: int):
    mapping = _mapping_row(db, _candidate_pk(candidate), jid)
    if mapping:
        for a in ("ai_score","ai_score_value"):
            if hasattr(mapping, a):
                return getattr(mapping, a)
    for a in ("ai_score","ai_score_value"):
        if hasattr(candidate, a):
            return getattr(candidate, a)
    return None


@router.post("/{candidate_id}/score/{jd_id}")
def post_score(candidate_id: int, jd_id: int, db: Session = Depends(get_db)):
    """
    Compute score & summary (calls Gemini). Persist ONLY the numeric score.
    Returns both score and summary to the client so the UI can show immediate explanation.
    """
    candidate = _get_candidate(db, candidate_id)
    job = _get_job(db, jd_id)
    if not candidate or not job:
        raise HTTPException(status_code=404, detail="Candidate or JD not found")

    cand_dict = _candidate_to_dict(candidate)
    # pass job title explicitly so prompt has the right context
    cand_dict["job_title"] = _job_title(job)

    jd_text, jd_link = _job_text_and_link(job)

    try:
        result = ai_score(cand_dict, jd_text=jd_text, jd_link=jd_link)
        score = int(result.get("score", 0))
        summary = result.get("summary", "") or ""
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scoring failed: {e}")

    # persist numeric score only
    try:
        _store_score_only(db, candidate, jd_id, score)
    except Exception:
        db.rollback()

    return {"candidate_id": candidate_id, "jd_id": jd_id, "score": score, "summary": summary}


@router.get("/{candidate_id}/explain/{jd_id}")
def get_explanation(candidate_id: int, jd_id: int, db: Session = Depends(get_db)):
    """
    Compute explanation on demand (calls Gemini) and return summary only (no DB write).
    """
    candidate = _get_candidate(db, candidate_id)
    job = _get_job(db, jd_id)
    if not candidate or not job:
        raise HTTPException(status_code=404, detail="Candidate or JD not found")

    cand_dict = _candidate_to_dict(candidate)
    cand_dict["job_title"] = _job_title(job)

    jd_text, jd_link = _job_text_and_link(job)
    try:
        result = ai_score(cand_dict, jd_text=jd_text, jd_link=jd_link)
        summary = result.get("summary", "") or "No explanation provided."
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Explain failed: {e}")
    return {"candidate_id": candidate_id, "jd_id": jd_id, "summary": summary}


@router.get("/{candidate_id}/score/{jd_id}")
def get_score(candidate_id: int, jd_id: int, db: Session = Depends(get_db)):
    candidate = _get_candidate(db, candidate_id)
    job = _get_job(db, jd_id)
    if not candidate or not job:
        raise HTTPException(status_code=404, detail="Candidate or JD not found")
    stored = _read_stored_score(db, candidate, jd_id)
    if stored is not None:
        return {"candidate_id": candidate_id, "jd_id": jd_id, "score": int(stored)}
    return post_score(candidate_id, jd_id, db)


@router.post("/{candidate_id}/reset-score/{jd_id}")
def reset_score(candidate_id: int, jd_id: int, db: Session = Depends(get_db)):
    candidate = _get_candidate(db, candidate_id)
    job = _get_job(db, jd_id)
    if not candidate or not job:
        raise HTTPException(status_code=404, detail="Candidate or JD not found")

    changed = False
    mapping = _mapping_row(db, _candidate_pk(candidate), jd_id)
    if mapping:
        for a in ("ai_score","ai_score_value"):
            if hasattr(mapping, a):
                setattr(mapping, a, None); changed = True
    for a in ("ai_score","ai_score_value"):
        if hasattr(candidate, a):
            setattr(candidate, a, None); changed = True
    if changed:
        db.commit()
    else:
        db.rollback()
    return {"message":"AI score reset","candidate_id":candidate_id,"jd_id":jd_id}
