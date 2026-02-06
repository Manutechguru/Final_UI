import sys
import os

# --- Ensure project imports work ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from landing_page_app.database import SessionLocal
from landing_page_app.models.candidates import Candidate
from landing_page_app.services.embedding_service import embed_text


# ---------- Helpers ----------

def clean(value: str | None) -> str | None:
    """
    Normalize dirty DB text into usable embedding input.
    """
    if not value:
        return None

    value = value.strip()

    if not value:
        return None

    if value.lower() in {"null", "none", "na", "n/a"}:
        return None

    return value


def build_embedding_text(candidate: Candidate) -> str | None:
    """
    Build canonical embedding text.
    Returns None ONLY if nothing usable exists.
    """
    parts = []

    skillset = clean(candidate.skillset)
    it_exp = clean(candidate.it_experience)
    rel_exp = clean(candidate.relevant_experience)
    location = clean(candidate.location)

    if skillset:
        parts.append(f"Skills: {skillset}")
    if it_exp:
        parts.append(f"Experience: {it_exp}")
    if rel_exp:
        parts.append(f"Relevant Experience: {rel_exp}")
    if location:
        parts.append(f"Location: {location}")

    return "\n".join(parts) if parts else None


# ---------- Main Backfill ----------

def main():
    db = SessionLocal()

    candidates = (
        db.query(Candidate)
        .filter(Candidate.embedding.is_(None))
        .all()
    )

    embedded = 0
    skipped = 0

    for candidate in candidates:
        try:
            text = build_embedding_text(candidate)

            if text is None:
                skipped += 1
                continue

            embedding = embed_text(text)
            if embedding is None:
                skipped += 1
                continue

            candidate.embedding = embedding
            db.add(candidate)
            embedded += 1

            # Debug first few rows ONLY
            if embedded <= 5:
                print(
                    f"DEBUG ID={candidate.candidates_id} | "
                    f"skillset={repr(candidate.skillset)} | "
                    f"it_exp={repr(candidate.it_experience)} | "
                    f"rel_exp={repr(candidate.relevant_experience)} | "
                    f"loc={repr(candidate.location)}"
                )

            if embedded % 20 == 0:
                print(f"✅ Embedded {embedded} candidates...")

        except Exception as e:
            print(f"❌ candidate_id={candidate.candidates_id}: {e}")
            db.rollback()

    db.commit()
    db.close()

    print("\n🎯 BACKFILL COMPLETE")
    print(f"✅ Embedded: {embedded}")
    print(f"⏭ Skipped (no usable text): {skipped}")


if __name__ == "__main__":
    main()
