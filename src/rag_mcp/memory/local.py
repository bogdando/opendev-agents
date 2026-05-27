"""Local file-based memory backend.

Memories are stored as markdown files with YAML frontmatter under a
configurable directory, organized by category. Recall uses keyword
overlap scoring (same approach as MockBackend for knowledge search).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from rag_mcp.constants import SEARCH_STOP_WORDS
from rag_mcp.memory import VALID_CATEGORIES

logger = logging.getLogger(__name__)

_EXTENSIONS = frozenset({".md"})


class LocalMemoryBackend:
    """Keyword-searchable file store for agent memories."""

    def __init__(self, memory_dir: str) -> None:
        self._root = Path(memory_dir)

    def _ensure_dir(self, category: str) -> Path:
        d = self._root / category
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def recall(
        self, query: str, category: str = "", top_k: int = 5
    ) -> list[dict]:
        """Find memories matching query by keyword overlap."""
        if not self._root.exists():
            return []

        memories = self._load_all(category)
        if not memories:
            return []

        keywords = [
            t
            for t in query.lower().split()
            if t not in SEARCH_STOP_WORDS and len(t) > 2
        ]
        if not keywords:
            keywords = query.lower().split()

        scored: list[tuple[float, dict]] = []
        for mem in memories:
            text = mem["content"].lower()
            hits = sum(1 for kw in keywords if kw in text)
            if hits > 0:
                score = hits / len(keywords)
                scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:top_k]]

    async def remember(
        self, content: str, category: str = "context"
    ) -> dict:
        """Write a memory to disk as a markdown file with frontmatter."""
        if category not in VALID_CATEGORIES:
            category = "context"

        cat_dir = self._ensure_dir(category)
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
        filename = f"{timestamp}_{content_hash}.md"
        filepath = cat_dir / filename

        if self._is_duplicate(content, cat_dir):
            existing = self._find_duplicate(content, cat_dir)
            return {
                "uri": str(existing.relative_to(self._root)),
                "category": category,
                "saved_at": now.isoformat(),
                "deduplicated": True,
            }

        frontmatter = {
            "category": category,
            "saved_at": now.isoformat(),
        }
        file_content = f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n\n{content}\n"
        filepath.write_text(file_content, encoding="utf-8")

        uri = str(filepath.relative_to(self._root))
        logger.info("Memory saved: %s (category=%s)", uri, category)
        return {
            "uri": uri,
            "category": category,
            "saved_at": now.isoformat(),
        }

    async def list_memories(
        self, category: str = "", limit: int = 20
    ) -> list[dict]:
        """List recent memories, optionally filtered by category."""
        memories = self._load_all(category)
        memories.sort(key=lambda m: m.get("saved_at", ""), reverse=True)
        return memories[:limit]

    def _load_all(self, category: str = "") -> list[dict]:
        """Load all memory files, optionally filtered by category."""
        if not self._root.exists():
            return []

        memories: list[dict] = []
        dirs = (
            [self._root / category]
            if category and (self._root / category).is_dir()
            else [
                d
                for d in self._root.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            ]
        )

        for d in dirs:
            for f in d.rglob("*"):
                if f.suffix in _EXTENSIONS and f.is_file():
                    mem = self._parse_memory_file(f)
                    if mem:
                        memories.append(mem)
        return memories

    def _parse_memory_file(self, path: Path) -> dict | None:
        """Parse a memory markdown file with YAML frontmatter."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None

        frontmatter: dict = {}
        content = text

        if text.startswith("---\n"):
            parts = text.split("---\n", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    pass
                content = parts[2].strip()

        return {
            "content": content,
            "category": frontmatter.get("category", path.parent.name),
            "saved_at": frontmatter.get("saved_at", ""),
            "uri": str(path.relative_to(self._root)),
        }

    def _is_duplicate(self, content: str, cat_dir: Path) -> bool:
        """Check if content already exists (simple hash-based dedup)."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
        return any(
            content_hash in f.name for f in cat_dir.iterdir() if f.is_file()
        )

    def _find_duplicate(self, content: str, cat_dir: Path) -> Path:
        """Find the existing file with matching content hash."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
        for f in cat_dir.iterdir():
            if f.is_file() and content_hash in f.name:
                return f
        return cat_dir / "unknown.md"
