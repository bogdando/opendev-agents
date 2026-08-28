"""OpenViking delegation backend for cross-session memory.

Delegates recall/remember to a running OpenViking instance via its
HTTP API. OV handles embedding-based semantic search and deduplication.
Requires a running OV server with embedding model configured.

After writing a memory via ``content/write``, a parallel write to the
``resources/memories/`` namespace is triggered so that OV's VLM pipeline
generates L0/L1 abstracts (``content/write`` never triggers VLM for
the ``memories/`` namespace).

Hybrid recall: OV's search is purely semantic (embedding-based). A
dedicated BM25 holder is filled independently, then always merged
into the semantic pool at BM25_MERGE_RATIO (30% of top_k). Lowest
semantic entries are dropped to make room. BM25 scores are aligned
so the best BM25 hit shares the max score of the kept semantic
pool; ties prefer BM25. Duplicate URIs are skipped. Date filters
prefer the URI filename timestamp over listing ``updated_at``.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from datetime import UTC, datetime

import httpx

from rag_mcp.constants import (
    BM25_MERGE_RATIO,
    KEYWORD_FALLBACK_LIST_LIMIT,
    LEAD_MATCH_CHARS,
    MIN_KEYWORD_COVERAGE,
    SEARCH_STOP_WORDS,
)
from rag_mcp.formatting import _L0_MAX_TOKENS, _L1_MAX_CHARS
from rag_mcp.memory import VALID_CATEGORIES

logger = logging.getLogger(__name__)

_L0_MAX_CHARS = _L0_MAX_TOKENS * 5
_VLM_ABSTRACT_MAX_CHARS = _L1_MAX_CHARS
_DEDUP_QUERY_MAX_CHARS = _L1_MAX_CHARS


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


def _query_keywords(query: str) -> list[str]:
    """Extract meaningful keywords from a query string."""
    return [
        t for t in query.lower().split()
        if t not in SEARCH_STOP_WORDS and len(t) > 2
    ] or query.lower().split()


def _keyword_overlap(text: str, keywords: list[str]) -> float:
    """Fraction of keywords found in text (0.0–1.0)."""
    if not keywords:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    return hits / len(keywords)


def _lead_match(text: str, keywords: list[str], window: int = LEAD_MATCH_CHARS) -> bool:
    """True when every query keyword appears in the opening *window* chars.

    Distinguishes a gold document whose body *is* the query from a
    citing document that quotes the same title later (workflow, notes).
    """
    if not keywords or not text:
        return False
    head = text.lstrip()[:window].lower()
    return all(kw in head for kw in keywords)


def _keyword_rank(text: str, keywords: list[str]) -> tuple[float, int]:
    """Sort key: overlap first, then lead-window match."""
    return (_keyword_overlap(text, keywords), 1 if _lead_match(text, keywords) else 0)


def _slot_counts(top_k: int) -> tuple[int, int]:
    """Return (n_semantic, n_bm25) for a 70/30 merge of *top_k* slots."""
    if top_k <= 0:
        return 0, 0
    n_bm25 = min(top_k, max(1, round(top_k * BM25_MERGE_RATIO)))
    return top_k - n_bm25, n_bm25


def _align_bm25_scores(bm25: list[dict], sem_max: float) -> None:
    """Scale BM25 scores so max(BM25) equals *sem_max* (in-place)."""
    if not bm25 or sem_max <= 0:
        return
    bm_max = max((r.get("score") or 0.0) for r in bm25)
    if bm_max <= 0:
        return
    scale = sem_max / bm_max
    for r in bm25:
        r["score"] = round((r.get("score") or 0.0) * scale, 4)


def _merge_bm25_proportion(
    semantic: list[dict],
    bm25: list[dict],
    top_k: int,
) -> list[dict]:
    """Keep 70% semantic slots, replace the rest with dedicated BM25 hits.

    BM25 URIs already in the kept semantic pool are skipped. If the
    holder has fewer hits than its quota, extra semantic entries are
    kept so the result still fills *top_k*. After score alignment,
    the list is sorted by score; BM25 wins ties so gold is not hidden
    behind a citing semantic hit with the same max relevance.
    """
    n_sem, n_bm25 = _slot_counts(top_k)
    sem_kept_preview = semantic[:n_sem]
    sem_uris = {r.get("uri") for r in sem_kept_preview}
    bm25_unique = [r for r in bm25 if r.get("uri") not in sem_uris][:n_bm25]
    n_bm25_actual = len(bm25_unique)
    n_sem_actual = min(len(semantic), top_k - n_bm25_actual)
    sem_kept = semantic[:n_sem_actual]
    if not bm25_unique:
        return semantic[:top_k]
    sem_max = max((r.get("score") or 0.0) for r in sem_kept) if sem_kept else 0.0
    _align_bm25_scores(bm25_unique, sem_max)
    for r in sem_kept:
        r["_pool"] = "semantic"
    for r in bm25_unique:
        r["_pool"] = "bm25"
    merged = sem_kept + bm25_unique
    merged.sort(
        key=lambda r: (
            r.get("score") or 0.0,
            1 if r.get("_pool") == "bm25" else 0,
        ),
        reverse=True,
    )
    for r in merged:
        r.pop("_pool", None)
    return merged[:top_k]


_TS_RE = re.compile(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z")


def _saved_at_from_uri(uri: str) -> str:
    """Extract ISO 8601 timestamp from a viking memory URI filename.

    URI example: ``viking://user/default/memories/context/20260826T112211Z.md``
    Returns: ``2026-08-26T11:22:11+00:00`` or empty string.
    """
    segment = uri.rsplit("/", 1)[-1] if uri else ""
    stem = segment.rsplit(".", 1)[0] if "." in segment else segment
    m = _TS_RE.match(stem)
    if not m:
        return ""
    y, mo, d, h, mi, s = m.groups()
    return f"{y}-{mo}-{d}T{h}:{mi}:{s}+00:00"


def _parse_iso_dt(value: str) -> datetime | None:
    """Parse an ISO 8601 date or datetime string to a tz-aware datetime.

    Accepts date-only (``2026-08-26``), datetime with offset, or datetime
    with ``Z`` suffix. Returns None on parse failure.
    """
    if not value:
        return None
    try:
        if "T" not in value and len(value) == 10:
            return datetime.fromisoformat(f"{value}T00:00:00+00:00")
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return None


def _filter_by_date(
    items: list[dict],
    dt_after: datetime | None,
    dt_before: datetime | None,
) -> list[dict]:
    """Keep only items whose saved_at falls within [dt_after, dt_before)."""
    filtered: list[dict] = []
    for item in items:
        ts = _parse_iso_dt(item.get("saved_at", ""))
        if ts is None:
            continue
        if dt_after and ts < dt_after:
            continue
        if dt_before and ts >= dt_before:
            continue
        filtered.append(item)
    return filtered


def _strip_frontmatter(text: str) -> str:
    """Remove YAML front-matter (``---...---``) from stored content."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4:].lstrip("\n")


def _build_memory_dict(
    raw_text: str,
    ov_detail: str,
    item: dict,
    uri: str,
    category: str,
    detail_level: str,
) -> dict:
    """Build a memory result dict, mapping OV's ``detail`` tier field.

    OV context-mode entries include ``detail`` (``"abstract"``,
    ``"overview"``, or ``"full"``).  When the served tier is lower
    than full, ``raw_text`` is the summary — route it to the
    appropriate sidecar and leave ``content`` empty (to be filled
    by ``_read_content`` when L2 is requested).
    """
    saved_at = (
        _saved_at_from_uri(uri)
        or item.get("saved_at")
        or item.get("updated_at")
    )
    mem: dict = {
        "content": "",
        "category": category,
        "saved_at": saved_at,
        "uri": uri,
        "score": item.get("score"),
    }

    raw_l0 = _strip_frontmatter(
        item.get("l0_summary") or item.get("abstract") or ""
    )
    raw_l1 = _strip_frontmatter(
        item.get("l1_summary") or item.get("overview") or ""
    )
    l0 = raw_l0 if len(raw_l0) < _L0_MAX_CHARS else ""
    l1 = raw_l1 if len(raw_l1) < _L1_MAX_CHARS else ""

    if ov_detail == "abstract":
        l0 = l0 or raw_text
        if detail_level == "L1":
            mem["content"] = raw_text
    elif ov_detail == "overview":
        l1 = l1 or raw_text
        mem["content"] = raw_text
        if not mem["content"] and not l1:
            mem["_fetch_full"] = True
    else:
        mem["content"] = raw_text

    if l0:
        mem["l0_summary"] = l0
    if l1:
        mem["l1_summary"] = l1

    return mem


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
        vlm_enabled: bool = False,
    ) -> None:
        self._url = url.rstrip("/")
        self._account = account
        self._user = user
        self._agent_id = agent_id
        self._dedup_threshold = dedup_threshold
        self._dedup_turns = dedup_turns
        self._vlm_enabled = vlm_enabled
        self._headers: dict[str, str] = {
            "X-OpenViking-Account": account,
            "X-OpenViking-User": user,
        }
        if api_key:
            self._headers["X-API-Key"] = api_key

    def _memory_prefix(self) -> str:
        return f"viking://user/{self._user}/memories"

    def _resource_prefix(self) -> str:
        return f"viking://user/{self._user}/resources/memories"

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

        OV's context-mode entries carry a ``detail`` field indicating
        which tier was served (``"abstract"``, ``"overview"``, or
        ``"full"``).  This is mapped to the ``l0_summary`` /
        ``l1_summary`` sidecars so the downstream formatter renders
        the correct tier without re-truncating.  Full content is
        fetched via ``_read_content()`` only when the caller requests
        L2 and the entry was served at a lower tier.
        """
        session_id = kwargs.get("session_id", "")
        detail_level = kwargs.get("detail_level", "L2")
        saved_after = kwargs.get("saved_after", "")
        saved_before = kwargs.get("saved_before", "")
        use_context = bool(self._dedup_turns and session_id)

        target_uri = self._memory_prefix()
        if category and category in VALID_CATEGORIES:
            target_uri = f"{target_uri}/{category}"

        # Always over-fetch x3: middleware needs headroom for keyword
        # post-filtering and date-range narrowing at all detail levels.
        search_limit = top_k * 3

        payload: dict = {
            "query": query,
            "limit": search_limit,
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

        vlm_abstracts: dict[str, str] = {}
        if self._vlm_enabled:
            vlm_abstracts = self._extract_resource_abstracts(
                result_data.get("resources", [])
            )
            if not vlm_abstracts and not use_context and items:
                needs_vlm = any(
                    not (it.get("abstract") or it.get("l0_summary"))
                    for it in items
                )
                if needs_vlm:
                    vlm_abstracts = await self._fetch_vlm_abstracts(
                        query, category, top_k
                    )

        results: list[dict] = []
        for item in items:
            uri = item.get("uri", "")
            raw_text = _strip_frontmatter(
                item.get("text") or item.get("content") or ""
            )
            cat = item.get("category") or _category_from_uri(uri)
            ov_detail = item.get("detail", "")

            mem = _build_memory_dict(
                raw_text, ov_detail, item, uri, cat, detail_level,
            )
            if not mem.get("l0_summary") and vlm_abstracts:
                fname = uri.rsplit("/", 1)[-1] if uri else ""
                vlm_l0 = vlm_abstracts.get(fname, "")
                if vlm_l0:
                    mem["l0_summary"] = vlm_l0
            fetch_full = mem.pop("_fetch_full", False)
            if not mem["content"] and uri and (detail_level == "L2" or fetch_full):
                mem["content"] = await self._read_content(uri)

            has_text = (
                mem["content"]
                or mem.get("l0_summary")
                or mem.get("l1_summary")
            )
            if has_text:
                results.append(mem)

        keywords = _query_keywords(query)

        # Semantic pool only — do not mix BM25 into these scores.
        results.sort(key=lambda r: r.get("score") or 0.0, reverse=True)

        # Date-range post-filter (client-side; OV search has no native support).
        dt_after = _parse_iso_dt(saved_after)
        dt_before = _parse_iso_dt(saved_before)
        if dt_after or dt_before:
            results = _filter_by_date(results, dt_after, dt_before)

        n_sem, n_bm25 = _slot_counts(top_k)
        sem_kept = results[:n_sem]
        bm25_holder = await self._keyword_fallback(
            query, keywords, category, detail_level,
            exclude_uris={r["uri"] for r in sem_kept},
            dt_after=dt_after,
            dt_before=dt_before,
            limit=n_bm25,
        )
        return _merge_bm25_proportion(results, bm25_holder, top_k)

    async def _keyword_fallback(
        self,
        query: str,
        keywords: list[str],
        category: str,
        detail_level: str,
        exclude_uris: set[str] | None = None,
        dt_after: datetime | None = None,
        dt_before: datetime | None = None,
        limit: int = 1,
    ) -> list[dict]:
        """Fill the dedicated BM25 holder from listed memories.

        Scans listed memories (category-scoped first, then all) and
        returns up to *limit* keyword matches not in *exclude_uris*.
        Date filters use the URI filename timestamp and run before the
        list cap so an older gold in a tight window is kept.
        Gracefully returns an empty list on any I/O error.
        """
        exclude_uris = exclude_uris or set()
        if limit <= 0:
            return []

        try:
            listing = await self.list_memories(
                category=category,
                limit=KEYWORD_FALLBACK_LIST_LIMIT,
                dt_after=dt_after,
                dt_before=dt_before,
            )
            if not listing and category:
                listing = await self.list_memories(
                    category="",
                    limit=KEYWORD_FALLBACK_LIST_LIMIT,
                    dt_after=dt_after,
                    dt_before=dt_before,
                )
        except (httpx.HTTPError, AttributeError, TypeError):
            return []

        if not listing:
            return []

        hits: list[tuple[tuple[float, int], dict]] = []
        reads = 0
        perfect = 0

        for item in listing:
            uri = item.get("uri", "")
            if not uri or uri in exclude_uris:
                continue
            item_ts = _parse_iso_dt(
                _saved_at_from_uri(uri) or item.get("saved_at")
            )
            if (dt_after or dt_before) and item_ts is None:
                continue
            if dt_after and item_ts and item_ts < dt_after:
                continue
            if dt_before and item_ts and item_ts >= dt_before:
                continue
            if reads >= KEYWORD_FALLBACK_LIST_LIMIT:
                break
            try:
                content = await self._read_content(uri)
            except (httpx.HTTPError, AttributeError, TypeError):
                logger.debug("Keyword fallback: failed to read %s", uri)
                continue
            reads += 1
            if not content:
                continue
            body = _strip_frontmatter(content)
            rank = _keyword_rank(body, keywords)
            if rank[0] < MIN_KEYWORD_COVERAGE:
                continue
            cat = _category_from_uri(uri)
            saved_at = _saved_at_from_uri(uri) or item.get("saved_at")
            hits.append((rank, {
                "content": body,
                "category": cat,
                "saved_at": saved_at,
                "uri": uri,
                "score": round(rank[0], 4),
            }))
            if rank[0] >= 1.0 and rank[1] == 1:
                perfect += 1
                if perfect >= limit:
                    break

        hits.sort(key=lambda t: t[0], reverse=True)
        return [h[1] for h in hits[:limit]]

    async def _fetch_vlm_abstracts(
        self, query: str, category: str, top_k: int,
    ) -> dict[str, str]:
        """Secondary search on ``resources/memories/`` for VLM abstracts."""
        resource_target = self._resource_prefix()
        if category and category in VALID_CATEGORIES:
            resource_target = f"{resource_target}/{category}"
        try:
            async with httpx.AsyncClient(timeout=5.0, http2=True) as client:
                resp = await client.post(
                    f"{self._url}/api/v1/search/search",
                    json={
                        "query": query,
                        "target_uri": resource_target,
                        "limit": top_k,
                    },
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError:
            return {}
        return self._extract_resource_abstracts(
            data.get("result", {}).get("resources", [])
        )

    @staticmethod
    def _extract_resource_abstracts(
        resources: list[dict],
    ) -> dict[str, str]:
        """Build a filename-to-abstract map from resource search results.

        Resources created by the dual-write VLM trigger live under
        ``resources/memories/<cat>/<file>.md/<file>.md``.  The trailing
        filename matches the memory file.  Only non-trivial VLM-generated
        abstracts (shorter than the full content) are kept.
        """
        abstracts: dict[str, str] = {}
        for res in resources:
            uri = res.get("uri", "")
            if "/resources/memories/" not in uri:
                continue
            raw = _strip_frontmatter(res.get("abstract", ""))
            if not raw or len(raw) > _VLM_ABSTRACT_MAX_CHARS:
                continue
            fname = uri.rsplit("/", 1)[-1] if uri else ""
            if fname and fname not in abstracts:
                abstracts[fname] = raw
        return abstracts

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
                    return _strip_frontmatter(result)
                raw = result.get("content", "") if isinstance(result, dict) else ""
                return _strip_frontmatter(raw)
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
            "query": (stub + content)[:_DEDUP_QUERY_MAX_CHARS],
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

    async def _trigger_vlm(
        self, full_content: str, category: str, filename: str,
    ) -> None:
        """Upload content to ``resources/memories/`` via add_resource.

        OV's VLM pipeline only runs for resources, not memories.  This
        fire-and-forget call creates a parallel resource so that VLM
        generates L0/L1 abstracts that recall can later pick up.
        """
        resource_uri = f"{self._resource_prefix()}/{category}/{filename}"
        try:
            async with httpx.AsyncClient(timeout=30.0, http2=True) as client:
                upload_resp = await client.post(
                    f"{self._url}/api/v1/resources/temp_upload",
                    files={"file": (filename, io.BytesIO(full_content.encode()))},
                    headers=self._headers,
                )
                upload_resp.raise_for_status()
                temp_id = (
                    upload_resp.json()
                    .get("result", {})
                    .get("temp_file_id", "")
                )
                if not temp_id:
                    logger.warning("VLM trigger: temp_upload returned no ID")
                    return

                add_resp = await client.post(
                    f"{self._url}/api/v1/resources",
                    json={
                        "temp_file_id": temp_id,
                        "to": resource_uri,
                        "wait": False,
                    },
                    headers=self._headers,
                )
                add_resp.raise_for_status()
                logger.info("VLM trigger: queued %s", resource_uri)
        except httpx.HTTPError as exc:
            logger.warning("VLM trigger failed for %s: %s", resource_uri, exc)

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
        if self._vlm_enabled:
            asyncio.ensure_future(
                self._trigger_vlm(frontmatter + content, category, f"{timestamp}.md")
            )
        return {
            "uri": uri,
            "category": category,
            "saved_at": now.isoformat(),
        }

    async def list_memories(
        self,
        category: str = "",
        limit: int = 20,
        dt_after: datetime | None = None,
        dt_before: datetime | None = None,
    ) -> list[dict]:
        """List memories via OV's filesystem listing.

        Date filters (URI filename timestamp) run before *limit* so a
        tight window still includes older gold.  *limit* 0 means no cap
        (tests).  Keyword fallback uses KEYWORD_FALLBACK_LIST_LIMIT.
        """
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
        for item in data.get("entries", data.get("items", [])):
            uri = item.get("uri", item.get("path", ""))
            results.append(
                {
                    "content": item.get("name", ""),
                    "category": category or _category_from_uri(uri),
                    "saved_at": _saved_at_from_uri(uri) or item.get("updated_at", ""),
                    "uri": uri,
                }
            )
        results.sort(key=lambda r: r.get("saved_at") or "", reverse=True)
        if dt_after or dt_before:
            results = _filter_by_date(results, dt_after, dt_before)
        if limit > 0:
            results = results[:limit]
        return results
