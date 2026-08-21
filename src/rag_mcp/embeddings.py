"""Thin async client for OpenAI-compatible /v1/embeddings endpoints.

Calls an external Llama Stack or Ollama service to generate embeddings.
Returns None on failure so callers can gracefully fall back to keyword
search without crashing.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Async HTTP client for embedding generation."""

    def __init__(self, base_url: str, model: str, api_key: str = "") -> None:
        self._url = f"{base_url.rstrip('/')}/v1/embeddings"
        self._model = model
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(timeout=30.0)

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Embed a batch of texts. Returns None on failure (graceful fallback)."""
        try:
            resp = await self._client.post(
                self._url,
                json={"model": self._model, "input": texts},
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Embedding request failed: %s", exc)
            return None

    async def embed_query(self, text: str) -> list[float] | None:
        """Embed a single query string."""
        result = await self.embed([text])
        return result[0] if result else None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
