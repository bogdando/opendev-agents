"""OpenViking delegation backend for cross-session memory.

Delegates recall/remember to a running OpenViking instance via its
HTTP API. OV handles embedding-based semantic search and deduplication.
Requires a running OV server with embedding model configured.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from rag_mcp.memory import VALID_CATEGORIES

logger = logging.getLogger(__name__)


class OpenVikingMemoryBackend:
    """Memory backend that delegates to OpenViking's HTTP API."""

    def __init__(
        self,
        url: str = "http://127.0.0.1:1933",
        account: str = "default",
        user: str = "developer",
        agent_id: str = "rag-mcp-server",
    ) -> None:
        self._url = url.rstrip("/")
        self._account = account
        self._user = user
        self._agent_id = agent_id
        self._headers = {
            "X-OpenViking-Account": account,
            "X-OpenViking-User": user,
        }

    def _memory_prefix(self) -> str:
        return f"viking://user/{self._user}/memories"

    async def recall(
        self, query: str, category: str = "", top_k: int = 5
    ) -> list[dict]:
        """Semantic search over stored memories via OV's search API."""
        target_uri = self._memory_prefix()
        if category and category in VALID_CATEGORIES:
            target_uri = f"{target_uri}/{category}"

        payload = {
            "query": query,
            "target_uri": target_uri,
            "limit": top_k,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
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

        results: list[dict] = []
        result_data = data.get("result", data)
        memories = result_data.get("memories", result_data.get("results", []))
        for item in memories:
            uri = item.get("uri", "")
            content = item.get("content", "")
            if not content and uri:
                content = await self._read_content(uri)
            results.append(
                {
                    "content": content,
                    "category": item.get("category", "context"),
                    "saved_at": item.get("saved_at", ""),
                    "uri": uri,
                }
            )
        return results

    async def _read_content(self, uri: str) -> str:
        """Fetch the actual content of a memory file from OV."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
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

    async def remember(
        self, content: str, category: str = "context"
    ) -> dict:
        """Store a memory in OpenViking via the content/write API."""
        if category not in VALID_CATEGORIES:
            category = "context"

        now = datetime.now(timezone.utc)
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
            async with httpx.AsyncClient(timeout=30.0) as client:
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
            async with httpx.AsyncClient(timeout=10.0) as client:
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
