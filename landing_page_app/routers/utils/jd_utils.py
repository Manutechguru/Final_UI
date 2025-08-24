# landing_page_app/utils/jd_utils.py

import re
import requests
from typing import Dict, List, Tuple


# -----------------------------
# Fetch JD Text from Google Docs / Drive
# -----------------------------
def fetch_jd_text(jd_link: str) -> str:
    """
    Fetch plain JD text from a Google Docs or Google Drive link.
    
    Supports:
        - Google Docs links (docs.google.com)
        - Google Drive share links (drive.google.com)
    
    Returns:
        str: Text content of the JD, empty string on failure.
    """
    try:
        # ---------------------
        # Handle Google Docs links
        # ---------------------
        if "docs.google.com" in jd_link:
            # Convert edit link to export TXT
            if "/edit" in jd_link:
                jd_link = jd_link.split("/edit")[0] + "/export?format=txt"
            elif "/view" in jd_link:
                jd_link = jd_link.split("/view")[0] + "/export?format=txt"

            response = requests.get(jd_link)
            response.raise_for_status()
            return response.text.strip()

        # ---------------------
        # Handle Google Drive links
        # ---------------------
        elif "drive.google.com" in jd_link:
            # Extract file ID
            match = re.search(r"/d/([a-zA-Z0-9_-]+)", jd_link)
            if not match:
                raise ValueError("Could not extract file ID from Drive link.")
            file_id = match.group(1)
            export_link = f"https://drive.google.com/uc?export=download&id={file_id}"

            response = requests.get(export_link)
            response.raise_for_status()
            return response.text.strip()

        else:
            raise ValueError("Unsupported JD link format.")

    except Exception as e:
        print(f"❌ Failed to fetch JD text from link '{jd_link}': {e}")
        return ""


# -----------------------------
# Extract Keywords from JD Text
# -----------------------------
def extract_jd_keywords(jd_text: str) -> Dict[str, List[str]]:
    """
    Parse JD text and extract keywords such as skills, tools, and locations.

    Returns:
        dict: {"skills": [...], "tools": [...], "locations": [...]}
    """
    keywords = {
        "skills": [],
        "tools": [],
        "locations": []
    }

    if not jd_text:
        return keywords

    # Tokenize words (alphanumeric + special chars like # + .)
    tokens = re.findall(r"[A-Za-z0-9\-\+\#\.]+", jd_text)

    # Keyword lists (can be extended)
    skill_keywords = [
        "python", "java", "aws", "docker", "kubernetes", "react",
        "angular", "node", "sql", "ml", "ai", "data", "pandas", "spark"
    ]

    tools_keywords = [
        "jira", "git", "jenkins", "tableau", "powerbi", "figma"
    ]

    location_keywords = [
        "remote", "hybrid", "onsite", "bangalore", "pune", "hyderabad",
        "mumbai", "chennai", "delhi", "gurgaon"
    ]

    # Extract keywords
    for token in tokens:
        lower = token.lower()
        if lower in skill_keywords:
            keywords["skills"].append(token)
        if lower in tools_keywords:
            keywords["tools"].append(token)
        if lower in location_keywords:
            keywords["locations"].append(token)

    # Deduplicate
    keywords = {k: list(set(v)) for k, v in keywords.items()}

    return keywords


# -----------------------------
# Combined JD Helper
# -----------------------------
def parse_jd(jd_link: str) -> Tuple[str, Dict[str, List[str]]]:
    """
    Fetch JD text and extract keywords.

    Returns:
        tuple: (jd_text, extracted_keywords)
    """
    jd_text = fetch_jd_text(jd_link)
    extracted = extract_jd_keywords(jd_text)
    return jd_text, extracted
