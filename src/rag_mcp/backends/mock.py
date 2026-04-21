"""Mock backend: keyword search over local text files.

Searches ``.md``, ``.rst``, ``.adoc``, and ``.txt`` files recursively
under each store subdirectory.  Directory layout expected under
*knowledge_dir*::

    knowledge/
    ├── openstack-docs/      <- store_id = "openstack-docs"
    │   ├── admin/
    │   │   └── scheduling.rst
    │   ├── l3-agent.md
    │   └── neutron-ovn.md
    └── openstack-code/      <- store_id = "openstack-code"
        └── nova-scheduler.md
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from rag_mcp.constants import SEARCH_STOP_WORDS

_TEXT_EXTENSIONS = frozenset((".md", ".rst", ".adoc", ".txt"))

_MAX_COVERAGE_ITEMS = 50


def _text_files(root: Path) -> list[Path]:
    """Return all searchable text files under *root*, recursively."""
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix in _TEXT_EXTENSIONS
    )


class MockBackend:
    """Keyword-match backend backed by a directory of text files."""

    def __init__(self, knowledge_dir: str) -> None:
        self._root = Path(knowledge_dir)

    def _store_dirs(self) -> list[Path]:
        if not self._root.is_dir():
            return []
        return sorted(
            p for p in self._root.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )

    async def list_stores(self) -> list[dict]:
        stores: list[dict] = []
        for d in self._store_dirs():
            files = _text_files(d)
            mtime = max(
                (f.stat().st_mtime for f in files), default=0.0
            )
            freshness = (
                datetime.fromtimestamp(
                    mtime, tz=timezone.utc
                ).isoformat()
                if mtime
                else "unknown"
            )
            coverage = sorted(
                f.stem.replace("-", " ") for f in files
            )[:_MAX_COVERAGE_ITEMS]
            stores.append(
                {
                    "id": d.name,
                    "name": d.name.replace("-", " ").title(),
                    "description": (
                        f"Local knowledge store"
                        f" ({len(files)} files)"
                    ),
                    "doc_count": len(files),
                    "last_updated": freshness,
                    "access": "public",
                    "freshness": freshness,
                    "coverage": coverage,
                }
            )
        return stores

    async def get_store(self, store_id: str) -> dict | None:
        for s in await self.list_stores():
            if s["id"] == store_id:
                return s
        return None

    async def search(
        self, query: str, store_id: str, top_k: int
    ) -> list[dict]:
        store_dir = self._root / store_id
        if not store_dir.is_dir():
            return []

        query_lower = query.lower()
        keywords = [
            kw
            for kw in query_lower.split()
            if kw not in SEARCH_STOP_WORDS
        ]
        if not keywords:
            keywords = query_lower.split()
        if not keywords:
            return []

        scored: list[tuple[float, Path, str]] = []

        for text_file in _text_files(store_dir):
            text = text_file.read_text(errors="replace")
            text_lower = text.lower()
            hits = sum(
                1 for kw in keywords if kw in text_lower
            )
            if hits > 0:
                score = hits / len(keywords)
                scored.append((score, text_file, text))

        scored.sort(key=lambda t: t[0], reverse=True)

        results: list[dict] = []
        for score, path, text in scored[:top_k]:
            title = _extract_title(text, path)
            rel = os.path.relpath(path, self._root)
            results.append(
                {
                    "text": text,
                    "source": rel,
                    "metadata": {
                        "title": title,
                        "store_id": store_id,
                        "file_path": str(path),
                    },
                }
            )
        return results


def _extract_title(text: str, path: Path) -> str:
    """Extract the first heading from markdown or RST text."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("# ").strip()
        # RST heading: non-empty line followed by an underline of
        # =, -, ~, ^, or " characters spanning at least its length.
        if (
            stripped
            and i + 1 < len(lines)
            and not stripped.startswith(".")
        ):
            next_line = lines[i + 1].strip()
            if (
                len(next_line) >= len(stripped)
                and next_line
                and set(next_line) <= set("=-~^\"")
            ):
                return stripped
    return path.stem.replace("-", " ").title()
