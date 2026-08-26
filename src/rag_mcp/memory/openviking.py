"""OpenViking delegation backend for cross-session memory.

Delegates recall/remember to a running OpenViking instance via its
HTTP API. OV handles embedding-based semantic search and deduplication.
Requires a running OV server with embedding model configured.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from rag_mcp.memory import VALID_CATEGORIES

logger = logging.getLogger(__name__)


def _category_from_uri(uri: str) -> str:
    """Extract category from a viking memory URI, e.g.
    ``viking://user/X/memories/learning/file.md`` → ``learning``.
    Falls back to ``context``.
    """
    parts = uri.split("/memories/")
    if len(parts) == 2:
        segment = parts[1].split("/")[0]
        if segment in VALID_CATEGORIES:
            return segment
    return "context"


class OpenVikingMemoryBackend:
    """Memory backend that delegates to OpenViking's HTTP API."""

    def __init__(
        self,
        url: str = "http://127.0.0.1:1933",
        account: str = "default",
        user: str = "developer",
        agent_id: str = "rag-mcp-server",
        api_key: str = "",
        dedup_threshold: float = 0.85,
        dedup_turns: int = 5,
    ) -> None:
        self._url = url.rstrip("/")
        self._account = account
        self._user = user
        self._agent_id = agent_id
        self._dedup_threshold = dedup_threshold
        self._dedup_turns = dedup_turns
        self._headers: dict[str, str] = {
            "X-OpenViking-Account": account,
            "X-OpenViking-User": user,
        }
        if api_key:
            self._headers["X-API-Key"] = api_key

    def _memory_prefix(self) -> str:
        return f"viking://user/{self._user}/memories"

    async def recall(
        self, query: str, category: str = "", top_k: int = 5, **kwargs
    ) -> list[dict]:
        """Semantic search over stored memories.

        When *session_id* is available and ``dedup_turns > 0``, uses
        OV's ``mode:"context"`` face which suppresses memories already
        returned in recent turns.  Context mode requires omitting
        ``target_uri`` and returns ``entries`` (with ``text`` field)
        instead of ``memories`` (with ``content`` field).

        Falls back to plain search (with ``target_uri``) when session
        dedup is disabled or no session_id is provided.
        """
        session_id = kwargs.get("session_id", "")
        use_context = bool(self._dedup_turns and session_id)

        target_uri = self._memory_prefix()
        if category and category in VALID_CATEGORIES:
            target_uri = f"{target_uri}/{category}"

        payload: dict = {
            "query": query,
            "limit": top_k,
        }
        if use_context:
            payload["mode"] = "context"
            payload["session_id"] = session_id
            payload["dedup_turns"] = self._dedup_turns
        else:
            payload["target_uri"] = target_uri

        try:
            async with httpx.AsyncClient(timeout=10.0, http2=True) as client:
                resp = await client.post(
                    f"{self._url}/api/v1/search/search",
                    json=payload,
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.error("OpenViking recall failed: %s", e)
            return []

        result_data = data.get("result", data)

        if use_context:
            items = result_data.get("entries", [])
        else:
            items = result_data.get(
                "memories", result_data.get("results", [])
            )

        results: list[dict] = []
        for item in items:
            uri = item.get("uri", "")
            content = item.get("text") or item.get("content") or ""
            if not content and uri:
                content = await self._read_content(uri)
            cat = item.get("category") or _category_from_uri(uri)
            mem = {
                "content": content,
                "category": cat,
                "saved_at": item.get("saved_at", ""),
                "uri": uri,
                "score": item.get("score"),
            }
            l0 = item.get("l0_summary") or item.get("abstract") or ""
            l1 = item.get("l1_summary") or item.get("overview") or ""
            if l0:
                mem["l0_summary"] = l0
            if l1:
                mem["l1_summary"] = l1
            results.append(mem)
        return results

    async def _read_content(self, uri: str) -> str:
        """Fetch the actual content of a memory file from OV."""
        try:
            async with httpx.AsyncClient(timeout=10.0, http2=True) as client:
                resp = await client.get(
                    f"{self._url}/api/v1/content/read",
                    params={"uri": uri},
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
                result = data.get("result", "")
                if isinstance(result, str):
                    return result
                return result.get("content", "") if isinstance(result, dict) else ""
        except httpx.HTTPError:
            return ""

    async def _find_duplicate(
        self, content: str, category: str
    ) -> dict | None:
        """Search for an existing memory similar to *content*.

        Returns the best match if its score exceeds the dedup threshold,
        otherwise ``None``.  The query includes a frontmatter stub so
        embeddings align with the stored documents (OV embeds the full
        file including YAML front-matter).
        """
        if self._dedup_threshold <= 0:
            return None

        target_uri = self._memory_prefix()
        if category and category in VALID_CATEGORIES:
            target_uri = f"{target_uri}/{category}"

        stub = f"---\ncategory: {category}\n---\n\n"
        payload = {
            "query": (stub + content)[:2000],
            "target_uri": target_uri,
            "limit": 1,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0, http2=True) as client:
                resp = await client.post(
                    f"{self._url}/api/v1/search/search",
                    json=payload,
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError:
            return None

        result_data = data.get("result", data)
        memories = result_data.get("memories", result_data.get("results", []))
        if not memories:
            return None

        best = memories[0]
        score = best.get("score", 0)
        if score >= self._dedup_threshold:
            logger.info(
                "Write-time dedup: score %.3f >= %.3f for %s",
                score, self._dedup_threshold, best.get("uri", "?"),
            )
            return best
        return None

    async def remember(
        self, content: str, category: str = "context"
    ) -> dict:
        """Store a memory in OpenViking via the content/write API.

        Before writing, searches for semantically similar existing
        memories.  If a match scores above ``dedup_threshold``, the
        write is skipped and the existing URI is returned with
        ``deduplicated=True``.
        """
        if category not in VALID_CATEGORIES:
            category = "context"

        dup = await self._find_duplicate(content, category)
        if dup:
            return {
                "uri": dup.get("uri", ""),
                "category": category,
                "saved_at": dup.get("saved_at", ""),
                "deduplicated": True,
            }

        now = datetime.now(UTC)
        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        uri = f"{self._memory_prefix()}/{category}/{timestamp}.md"

        frontmatter = (
            f"---\ncategory: {category}\n"
            f"saved_at: {now.isoformat()}\n"
            f"agent_id: {self._agent_id}\n---\n\n"
        )

        payload = {
            "uri": uri,
            "content": frontmatter + content,
            "mode": "create",
            "wait": True,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0, http2=True) as client:
                resp = await client.post(
                    f"{self._url}/api/v1/content/write",
                    json=payload,
                    headers=self._headers,
                )
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("OpenViking remember failed: %s", e)
            return {
                "uri": uri,
                "category": category,
                "saved_at": now.isoformat(),
                "error": str(e),
            }

        logger.info("Memory stored in OpenViking: %s", uri)
        return {
            "uri": uri,
            "category": category,
            "saved_at": now.isoformat(),
        }

    async def list_memories(
        self, category: str = "", limit: int = 20
    ) -> list[dict]:
        """List memories via OV's filesystem listing."""
        list_path = self._memory_prefix()
        if category and category in VALID_CATEGORIES:
            list_path = f"{list_path}/{category}"

        params = {"path": list_path}

        try:
            async with httpx.AsyncClient(timeout=10.0, http2=True) as client:
                resp = await client.get(
                    f"{self._url}/api/v1/fs/ls",
                    params=params,
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.error("OpenViking list_memories failed: %s", e)
            return []

        results: list[dict] = []
        for item in data.get("entries", data.get("items", []))[:limit]:
            results.append(
                {
                    "content": item.get("name", ""),
                    "category": category or "context",
                    "saved_at": item.get("updated_at", ""),
                    "uri": item.get("uri", item.get("path", "")),
                }
            )
        return results
