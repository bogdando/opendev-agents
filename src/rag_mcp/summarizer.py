"""Thin async client for Ollama/OpenAI-compatible chat completions.

Used to generate L0/L1 summaries for knowledge files. Fires background
tasks so the search response is never blocked on summarization.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Coroutine

import httpx

logger = logging.getLogger(__name__)

_THINK_OPEN = "<think"
_THINK_CLOSE = "</think>"
# Some servers emit the closing tag with a trailing slash; the
# strip logic accepts either form and cuts after the last
# occurrence of any variant.
_THINK_CLOSE_VARIANTS = (_THINK_CLOSE, "</think/>")
_DIRECT_ANSWER_LABEL = "Direct answer"
# Sentinel the summarizer prompts ask the model to open its response
# with, built from the tag constants so the prompt and the strip
# logic cannot drift apart.
_SENTINEL = f"{_THINK_OPEN}>{_DIRECT_ANSWER_LABEL}{_THINK_CLOSE}"

_L0_SYSTEM = (
    "You are a concise summarizer. Produce a single sentence "
    "(max 100 tokens) capturing the document's main point. "
    "Do not include planning, reasoning or notes about the summary "
    "itself. "
    f"Start your response text with {_SENTINEL}"
)
_L1_SYSTEM = (
    "You are a concise summarizer. Produce a brief overview "
    "(max 500 words) of the document, preserving key facts and "
    "structure. Do not include planning, reasoning or notes about "
    "the summary itself. "
    f"Start your response text with {_SENTINEL}"
)


_L0_MAX_TOKENS = 150
_L1_MAX_TOKENS = 1024

# Sentence starters typical for chain-of-thought planning that models
# leak as plain prose when they ignore the sentinel prompt (e.g.
# "I'll structure the summary clearly: ..."). Only leading sentences
# are matched, so first-person prose mid-summary is preserved.
_META_STARTERS = (
    "I'll ", "I'm ", "I'd", "I ", "We ", "We'll ", "We'd ",
    "Let me ", "Let's ", "Let us ", "Keep it",
    "Allright, ", "Ok, ", "The user wants ",
    "The user asks", "The user needs "
)

# Sentence boundary: [.!?] followed by whitespace. The whitespace is
# consumed with the following sentence so the retained remainder keeps
# its original formatting.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _last_close_tag_end(text: str) -> int:
    """Index just past the last close tag of any accepted variant,
    or -1 when the text contains no close tag at all."""
    end = -1
    for variant in _THINK_CLOSE_VARIANTS:
        pos = text.rfind(variant)
        if pos != -1:
            end = max(end, pos + len(variant))
    return end


def strip_thinking(text: str) -> str:
    """Drop reasoning steps from reasoning-model output.

    Reasoning models (DeepSeek-R1, Qwen3 with thinking enabled) emit
    chain-of-thought inside <think>...</think> blocks (the closing
    tag may carry a trailing slash) followed by the final answer.
    Keep only the text after the last closing tag.

    Two degraded forms are also handled:

    * an unclosed <think> block, or a truncated sentinel prefix
      ("<think>Direct answer" with no closing tag): keep only the
      trailing segment after the last opening tag, dropping any
      leftover label remnant;
    * no tags at all, with chain-of-thought planning leaked as plain
      prose ("I'll structure the summary clearly: ..."): leading
      meta-planning sentences are removed by ``strip_meta_preamble``.

    Return the input unchanged when no reasoning is detected.
    """

    end = _last_close_tag_end(text)
    if end != -1:
        text = text[end:]
    elif _THINK_OPEN in text:
        # Unclosed reasoning block, or the model emitted the opening
        # half of the sentinel without the closing tag. Best effort:
        # keep the trailing segment and drop label remnants.
        text = text.rsplit(_THINK_OPEN, 1)[-1].removeprefix(">").lstrip()
        if text.startswith(_DIRECT_ANSWER_LABEL):
            text = text[len(_DIRECT_ANSWER_LABEL):].lstrip(":\n ")
    return strip_meta_preamble(text.strip())


def strip_meta_preamble(text: str) -> str:
    """Remove leading meta-planning sentences from a summary.

    Models that ignore the sentinel prompt leak chain-of-thought
    planning as plain text before the actual answer, e.g.
    ``"I'll structure the summary clearly: ... Keep it factual
    without markdown, under 500 words."``. Leading sentences whose
    first words reference the response itself (first-person planning
    or response-shaping imperatives) are dropped; stripping stops at
    the first content sentence, so prose that merely contains such
    phrases mid-text is preserved verbatim.

    Returns the input unchanged when no leading meta sentence matches.
    """
    stripped = text.strip()
    if not stripped:
        return stripped

    starts = [0]
    starts.extend(m.end() for m in _SENTENCE_END.finditer(text))
    kept = 0
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        sentence = text[start:end]
        if sentence.lstrip().startswith(_META_STARTERS):
            kept = i + 1
            continue
        break
    if kept == 0:
        return stripped
    if kept >= len(starts):
        # Every sentence was meta-planning; nothing survives.
        return ""
    return text[starts[kept]:].lstrip()


class Summarizer:
    """Generates L0/L1 text summaries via chat completions."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 180.0,
        api_key: str = "",
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/chat/completions"
        self._model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers)

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
                    "allowed_openai_params": ["reasoning_effort"],
                    "reasoning_effort": "low",
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = strip_thinking(
                data["choices"][0]["message"]["content"]
            )
            # An empty result means only reasoning leaked: treat it
            # as a failed generation so sidecars are not polluted.
            return content or None
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
