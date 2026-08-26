"""Thin async client for Ollama/OpenAI-compatible chat completions.

Used to generate L0/L1 summaries for knowledge files. Fires background
tasks so the search response is never blocked on summarization.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine

import httpx

logger = logging.getLogger(__name__)

_L0_SYSTEM = (
    "You are a concise summarizer. Produce a single sentence "
    "(max 100 tokens) capturing the document's main point."
)
_L1_SYSTEM = (
    "You are a concise summarizer. Produce a brief overview "
    "(max 500 words) of the document, preserving key facts and structure."
)


_L0_MAX_TOKENS = 150
_L1_MAX_TOKENS = 1024


class Summarizer:
    """Generates L0/L1 text summaries via chat completions."""

    def __init__(
        self, base_url: str, model: str, timeout: float = 180.0
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/chat/completions"
        self._model = model
        self._client = httpx.AsyncClient(timeout=timeout)

    async def generate_l0(self, text: str) -> str | None:
        """Generate a one-sentence abstract (~100 tokens)."""
        return await self._chat(
            system=_L0_SYSTEM,
            user=f"Summarize:\n\n{text[:4000]}",
            max_tokens=_L0_MAX_TOKENS,
        )

    async def generate_l1(self, text: str) -> str | None:
        """Generate an overview paragraph (~500 words)."""
        return await self._chat(
            system=_L1_SYSTEM,
            user=f"Summarize:\n\n{text[:8000]}",
            max_tokens=_L1_MAX_TOKENS,
        )

    async def _chat(
        self, system: str, user: str, max_tokens: int = _L1_MAX_TOKENS
    ) -> str | None:
        """Call the chat completions endpoint."""
        try:
            resp = await self._client.post(
                self._url,
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.0,
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            logger.warning("Summarizer request failed: %s", exc)
            return None


class BackgroundSummarizer:
    """Wraps Summarizer to fire-and-forget L0/L1 generation tasks.

    Callers register a callback that receives (file_key, l0, l1) when
    generation completes. This allows the sidecar manager to persist
    results without blocking search responses.
    """

    def __init__(
        self,
        summarizer: Summarizer,
        on_complete: Callable[[str, str | None, str | None], Coroutine],
    ) -> None:
        self._summarizer = summarizer
        self._on_complete = on_complete
        self._pending: set[str] = set()

    def schedule(self, file_key: str, text: str) -> None:
        """Schedule background L0/L1 generation for *file_key*.

        Deduplicates: if a task for this key is already pending, skips.
        """
        if file_key in self._pending:
            return
        self._pending.add(file_key)
        asyncio.get_event_loop().create_task(
            self._run(file_key, text)
        )

    async def _run(self, file_key: str, text: str) -> None:
        try:
            l0 = await self._summarizer.generate_l0(text)
            l1 = await self._summarizer.generate_l1(text)
            await self._on_complete(file_key, l0, l1)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Background summarization failed for %s: %s", file_key, exc
            )
        finally:
            self._pending.discard(file_key)

    @property
    def pending_count(self) -> int:
        return len(self._pending)
