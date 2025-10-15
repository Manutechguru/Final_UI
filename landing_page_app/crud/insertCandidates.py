# REPLACE THE WHOLE FILE WITH THIS CONTENT

from typing import Dict, Any, List
from sqlalchemy.orm import Session
from fastapi import UploadFile
import csv
import io

from landing_page_app.models import Candidate

def insert_candidates_from_csv(db: Session, csv_file: UploadFile) -> Dict[str, Any]:
    """
    Reads a CSV UploadFile and inserts Candidate rows.
    Returns a summary dict with message, duplicates, and inserted count.
    """
    content = csv_file.file.read()
    text = content.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    duplicates: List[Dict[str, Any]] = []
    count_inserted = 0

    for row in reader:
        # Example: adapt to your candidate unique constraints (e.g., email)
        email = (row.get("email") or row.get("Email") or "").strip().lower()
        if not email:
            continue

        exists = db.query(Candidate).filter(Candidate.email == email).first()
        if exists:
            duplicates.append({"email": email})
            continue

        cand = Candidate(
            name=row.get("name") or row.get("Name"),
            email=email,
            phone=row.get("phone") or row.get("Phone"),
            # Map other fields as needed...
        )
        db.add(cand)
        count_inserted += 1

    db.commit()

    message = f"Inserted {count_inserted} candidate(s); {len(duplicates)} duplicate(s) skipped."
    return {
        "message": message,
        "duplicates": duplicates,
        "inserted": count_inserted,
    }
