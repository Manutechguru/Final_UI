# landing_page_app/services/embedding_service.py

from typing import List
from sentence_transformers import SentenceTransformer

_model = SentenceTransformer("all-MiniLM-L6-v2")  # 384-dim

def embed_text(text: str) -> List[float] | None:
    if not text or not text.strip():
        return None

    embedding = _model.encode(
        text,
        normalize_embeddings=True
    )

    return embedding.tolist()
