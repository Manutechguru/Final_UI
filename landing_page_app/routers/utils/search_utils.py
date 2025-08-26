# landing_page_app/utils/search_utils.py

from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from landing_page_app.models.candidates import Candidate
import re

# -----------------------------
# BASIC SEARCH
# -----------------------------
def search_candidates(db: Session, search_query: str) -> List[Candidate]:
    """
    Basic search based on name, email, skillset, or company.
    """
    return db.query(Candidate).filter(
        or_(
            Candidate.candidate_name.ilike(f"%{search_query}%"),
            Candidate.email.ilike(f"%{search_query}%"),
            Candidate.skillset.ilike(f"%{search_query}%"),
            Candidate.company.ilike(f"%{search_query}%")
        )
    ).all()


# -----------------------------
# ADVANCED SEARCH (with filters)
# -----------------------------
def advanced_search_candidates(
    db: Session,
    skillset: Optional[str] = None,
    location: Optional[str] = None,
    min_exp: Optional[int] = None,
    max_exp: Optional[int] = None
) -> List[Candidate]:
    """
    Advanced candidate filtering by skillset, location, and experience range.
    Experience is parsed from text using parse_text_experience_to_months.
    """
    query = db.query(Candidate)

    if skillset:
        query = query.filter(Candidate.skillset.ilike(f"%{skillset}%"))
    if location:
        query = query.filter(Candidate.location.ilike(f"%{location}%"))

    candidates = query.all()
    filtered = []

    for c in candidates:
        months = parse_text_experience_to_months(c.it_experience)
        if min_exp is not None and months < min_exp:
            continue
        if max_exp is not None and months > max_exp:
            continue
        filtered.append(c)

    return filtered


# -----------------------------
# PARSE EXPERIENCE TEXT TO MONTHS
# -----------------------------
def parse_text_experience_to_months(text: str) -> int:
    """
    Converts experience text like '2 years 3 months' or '5 yrs' into total months.
    Returns 0 if input is invalid or empty.
    """
    if not text:
        return 0

    text = text.lower()
    years = months = 0

    # Match years
    match_years = re.search(r"(\d+)\s*(?:year|yr|years|yrs)", text)
    if match_years:
        years = int(match_years.group(1))

    # Match months
    match_months = re.search(r"(\d+)\s*(?:month|months|mo)", text)
    if match_months:
        months = int(match_months.group(1))

    return years * 12 + months


# -----------------------------
# PARSE EXPERIENCE FILTER INPUT
# -----------------------------
def parse_experience_filter_input(exp_input: str):
    """
    Parse experience filter text into a (min_exp, max_exp) tuple in months.
    Examples:
        "2-5"         => (24, 60)
        "3+"          => (36, None)
        "5"           => (60, 60)
        "0-1"         => (0, 12)
        "" or None    => (None, None)
    """
    if not exp_input or not isinstance(exp_input, str):
        return None, None

    exp_input = exp_input.strip().lower()
    min_exp = max_exp = None

    # Case 1: Range like "2-5"
    range_match = re.match(r"^(\d+)\s*-\s*(\d+)$", exp_input)
    if range_match:
        min_exp = int(range_match.group(1)) * 12
        max_exp = int(range_match.group(2)) * 12
        return min_exp, max_exp

    # Case 2: "3+" meaning minimum 3 years
    plus_match = re.match(r"^(\d+)\s*\+$", exp_input)
    if plus_match:
        min_exp = int(plus_match.group(1)) * 12
        return min_exp, None

    # Case 3: Single number "5"
    single_match = re.match(r"^(\d+)$", exp_input)
    if single_match:
        min_exp = max_exp = int(single_match.group(1)) * 12
        return min_exp, max_exp

    return None, None
