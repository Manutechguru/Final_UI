# landing_page_app/services/llm_service.py

from typing import List, Dict
import json
import os
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def evaluate_candidates_batch(
    jd_text: str,
    candidates: List[Dict],
) -> List[Dict]:
    """
    MUST return:
    [
      {
        "candidate_id": int,
        "ai_score": int
      }
    ]
    """

    prompt = f"""
You are a strict ATS scoring engine.

JOB DESCRIPTION:
{jd_text}

CANDIDATES:
{json.dumps(candidates, ensure_ascii=False)}

RULES:
- Score each candidate from 0 to 100
- Return ONLY valid JSON
- No explanations
- No markdown
- No text outside JSON

FORMAT:
[
  {{ "candidate_id": 1, "ai_score": 78 }},
  {{ "candidate_id": 2, "ai_score": 82 }}
]
"""

    resp = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=1024,
    )

    raw = resp.choices[0].message.content.strip()

    # ✅ DEBUG — THIS IS THE ONLY PLACE IT IS ALLOWED
    print("🔥 GROQ RAW RESPONSE:", raw)

    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return data
    except Exception:
        print("❌ LLM INVALID JSON:", raw)
        return []
