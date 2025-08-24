# landing_page_app/utils/ai_utils.py

import os
import requests
from typing import Dict, Any

# -----------------------------
# Gemini API Config
# -----------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"


# -----------------------------
# Score Candidate Using Gemini AI
# -----------------------------
def score_candidate(candidate_data: Dict[str, Any], jd_text: str) -> Dict[str, Any]:
    """
    Uses Gemini AI to score a candidate based on job description & profile.
    If Gemini API fails, falls back to heuristic scoring.
    """
    try:
        headers = {"Content-Type": "application/json"}
        params = {"key": GEMINI_API_KEY}

        prompt = f"""
        You are an AI recruitment assistant.
        Based on the following Job Description and Candidate Resume, 
        provide a matching score between 0 and 100.

        Job Description:
        {jd_text}

        Candidate Profile:
        Name: {candidate_data.get('candidate_name')}
        Email: {candidate_data.get('email')}
        Skills: {candidate_data.get('skillset')}
        Experience: {candidate_data.get('relevant_exp')}
        Education: {candidate_data.get('education')}
        Company: {candidate_data.get('company')}

        Respond in JSON format:
        {{
            "score": <int>,
            "summary": "<why this candidate is a good/bad fit>"
        }}
        """

        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        response = requests.post(GEMINI_API_URL, headers=headers, params=params, json=payload)

        if response.status_code == 200:
            data = response.json()
            # Extract response
            ai_response = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return {
                "score": extract_score(ai_response),
                "summary": extract_summary(ai_response)
            }

        # Fallback to heuristic scoring if Gemini fails
        return heuristic_scoring(candidate_data, jd_text)

    except Exception as e:
        print(f"Gemini AI scoring failed: {e}")
        return heuristic_scoring(candidate_data, jd_text)


# -----------------------------
# Extract score from AI response
# -----------------------------
def extract_score(ai_response: str) -> int:
    try:
        import re
        match = re.search(r'"score"\s*:\s*(\d+)', ai_response)
        return int(match.group(1)) if match else 0
    except:
        return 0


# -----------------------------
# Extract summary from AI response
# -----------------------------
def extract_summary(ai_response: str) -> str:
    try:
        import re
        match = re.search(r'"summary"\s*:\s*"([^"]+)"', ai_response)
        return match.group(1) if match else "Summary not available."
    except:
        return "Summary not available."


# -----------------------------
# Fallback: Heuristic Scoring
# -----------------------------
def heuristic_scoring(candidate_data: Dict[str, Any], jd_text: str) -> Dict[str, Any]:
    """
    Fallback scoring based on keyword matching if Gemini API fails.
    """
    skills = candidate_data.get("skillset", "").lower().split(",")
    jd_lower = jd_text.lower()

    # Count matched skills
    matched_skills = [s for s in skills if s.strip() and s.strip() in jd_lower]
    score = int((len(matched_skills) / max(len(skills), 1)) * 100)

    return {
        "score": score,
        "summary": f"Matched {len(matched_skills)} out of {len(skills)} skills"
    }
