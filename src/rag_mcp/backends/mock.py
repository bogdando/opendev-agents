"""Mock backend: keyword search over local markdown files.

Directory layout expected under *knowledge_dir*::

    knowledge/
    ├── openstack-docs/      <- store_id = "openstack-docs"
    │   ├── l3-agent.md
    │   └── neutron-ovn.md
    └── openstack-code/      <- store_id = "openstack-code"
        └── nova-scheduler.md
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


class MockBackend:
    """Keyword-match backend backed by a directory of markdown files."""

    def __init__(self, knowledge_dir: str) -> None:
        self._root = Path(knowledge_dir)

    def _store_dirs(self) -> list[Path]:
        if not self._root.is_dir():
            return []
        return sorted(
            p for p in self._root.iterdir() if p.is_dir() and not p.name.startswith(".")
        )

    async def list_stores(self) -> list[dict]:
        stores: list[dict] = []
        for d in self._store_dirs():
            md_files = list(d.glob("*.md"))
            mtime = max((f.stat().st_mtime for f in md_files), default=0.0)
            stores.append(
                {
                    "id": d.name,
                    "name": d.name.replace("-", " ").title(),
                    "description": f"Local markdown knowledge store ({len(md_files)} files)",
                    "doc_count": len(md_files),
                    "last_updated": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
                    if mtime
                    else "unknown",
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
        keywords = query_lower.split()
        scored: list[tuple[float, Path, str]] = []

        for md_file in store_dir.glob("*.md"):
            text = md_file.read_text(errors="replace")
            text_lower = text.lower()
            hits = sum(1 for kw in keywords if kw in text_lower)
            if hits > 0:
                score = hits / len(keywords)
                scored.append((score, md_file, text))

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
    """Pull the first markdown heading, or fall back to filename."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("# ").strip()
    return path.stem.replace("-", " ").title()
