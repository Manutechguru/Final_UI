# landing_page_app/crud/insertCandidates.py
import csv
from landing_page_app.models.candidates import Candidate
from sqlalchemy.orm import Session

def insert_candidates_from_csv(db: Session, csv_file) -> dict:
    try:
        contents = csv_file.file.read().decode("utf-8").splitlines()
        reader = csv.DictReader(contents)

        count_inserted = 0
        duplicates = []

        for row in reader:
            name = row.get("full_name")
            email = row.get("email")

            # Check if candidate already exists (by name + email)
            existing = db.query(Candidate).filter(
                Candidate.candidate_name == name,
                Candidate.email == email
            ).first()

            if existing:
                duplicates.append(name)
                continue

            candidate = Candidate(
                candidate_name=name,
                email=email,
                contact=row.get("phone"),
                location=row.get("location"),
                skillset=row.get("skillset"),
                relevant_experience=row.get("relevant_experience"),
                it_experience=row.get("it_experience"),
                education=row.get("education"),
                company=row.get("company"),
                resumelinks=row.get("resumelinks"),
                comment=row.get("comment"),
                clients=row.get("clients"),
                notice_period=row.get("notice_period")
            )
            db.add(candidate)
            count_inserted += 1

        db.commit()

        message = f"{count_inserted} candidates uploaded successfully."
        if duplicates:
            message += f" {len(duplicates)} duplicates skipped."

        return {
            "message": message,
            "duplicates": duplicates
        }
    except Exception as e:
        db.rollback()
        raise e
