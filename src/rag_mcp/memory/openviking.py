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
        url: str = "http://localhost:1933",
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
        return f"viking://agent/{self._agent_id}/memories"

    async def recall(
        self, query: str, category: str = "", top_k: int = 5
    ) -> list[dict]:
        """Semantic search over stored memories via OV's search API."""
        search_path = self._memory_prefix()
        if category and category in VALID_CATEGORIES:
            search_path = f"{search_path}/{category}"

        payload = {
            "query": query,
            "path": search_path,
            "top_k": top_k,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._url}/api/v1/search",
                    json=payload,
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.error("OpenViking recall failed: %s", e)
            return []

        results: list[dict] = []
        for item in data.get("results", []):
            results.append(
                {
                    "content": item.get("content", ""),
                    "category": item.get("metadata", {}).get(
                        "category", "context"
                    ),
                    "saved_at": item.get("metadata", {}).get("saved_at", ""),
                    "uri": item.get("uri", ""),
                }
            )
        return results

    async def remember(
        self, content: str, category: str = "context"
    ) -> dict:
        """Store a memory in OpenViking via the resources API."""
        if category not in VALID_CATEGORIES:
            category = "context"

        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        uri = f"{self._memory_prefix()}/{category}/{timestamp}.md"

        payload = {
            "uri": uri,
            "content": content,
            "metadata": {
                "category": category,
                "saved_at": now.isoformat(),
                "agent_id": self._agent_id,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._url}/api/v1/resources",
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

        params = {"path": list_path, "limit": limit}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._url}/api/v1/resources",
                    params=params,
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.error("OpenViking list_memories failed: %s", e)
            return []

        results: list[dict] = []
        for item in data.get("items", []):
            results.append(
                {
                    "content": item.get("content", item.get("name", "")),
                    "category": item.get("metadata", {}).get(
                        "category", category or "context"
                    ),
                    "saved_at": item.get("metadata", {}).get("saved_at", ""),
                    "uri": item.get("uri", ""),
                }
            )
        return results
