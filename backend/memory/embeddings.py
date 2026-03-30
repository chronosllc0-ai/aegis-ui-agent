"""Embedding generation for the memory system."""

from __future__ import annotations

import hashlib
import logging
import math

import httpx

logger = logging.getLogger(__name__)
EMBEDDING_DIM = 1536


async def get_embedding(text: str, api_key: str | None = None, provider: str = "openai") -> list[float]:
    """Generate an embedding for text with API fallback to deterministic hash."""
    if api_key and provider == "openai":
        return await _openai_embedding(text, api_key)
    return _hash_embedding(text)


async def _openai_embedding(text: str, api_key: str) -> list[float]:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "text-embedding-3-small", "input": text},
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
    except Exception:
        logger.warning("OpenAI embedding failed, using hash fallback", exc_info=True)
        return _hash_embedding(text)


def _hash_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    text_bytes = text.lower().strip().encode("utf-8")
    digest = hashlib.sha512(text_bytes).hexdigest()
    vector: list[float] = []
    seed = digest
    while len(vector) < dim:
        seed = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        for i in range(0, len(seed) - 1, 2):
            if len(vector) >= dim:
                break
            byte_val = int(seed[i : i + 2], 16)
            vector.append((byte_val / 255.0) * 2 - 1)
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
