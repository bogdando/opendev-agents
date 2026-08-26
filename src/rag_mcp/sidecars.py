"""Sidecar file management for L0/L1 summaries.

Handles reading, writing, freshness checking, and content-length
threshold logic. Sidecars are stored alongside knowledge files (mock)
or in a dedicated cache directory (solr/confluence).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_L0_TOKEN_THRESHOLD = 100
_L1_CHAR_THRESHOLD = 2000
_SAFE_CACHE_KEY = re.compile(r"^[A-Za-z0-9._-]+$")


def cache_key(doc_id: str) -> str:
    """Map a document id to a single path component under the cache dir.

    Simple ids (``doc123``) are kept for readability. URLs and paths are
    hashed so they cannot create nested directories or escape the cache
    root (``https://.../solutions/3109111`` → 32-char hex).
    """
    if doc_id and _SAFE_CACHE_KEY.fullmatch(doc_id):
        return doc_id
    return hashlib.sha256(doc_id.encode()).hexdigest()[:32]


def content_hash(text: str) -> str:
    """SHA-256 prefix used as freshness fingerprint."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def needs_l0(text: str) -> bool:
    """Return True if the content is long enough to benefit from L0."""
    approx_tokens = len(text.split())
    return approx_tokens > _L0_TOKEN_THRESHOLD


def needs_l1(text: str) -> bool:
    """Return True if the content is long enough to benefit from L1."""
    return len(text) > _L1_CHAR_THRESHOLD


class SidecarManager:
    """Manages L0/L1 sidecar files for a knowledge store directory."""

    def __init__(self, store_dir: Path, summaries_dir: Path | None = None) -> None:
        self._store_dir = store_dir
        self._summaries_dir = summaries_dir
        self._state_file = (summaries_dir or store_dir) / ".ingest-state.json"
        self._state: dict[str, dict] = self._load_state()

    def _load_state(self) -> dict[str, dict]:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_state(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(
            json.dumps(self._state, indent=2), encoding="utf-8"
        )

    def _sidecar_path(self, file_path: Path, level: str) -> Path:
        """Resolve sidecar file path (.l0 or .l1)."""
        if self._summaries_dir:
            rel = file_path.relative_to(self._store_dir)
            return self._summaries_dir / f"{rel}.{level}"
        return file_path.parent / f"{file_path.name}.{level}"

    def get_l0(self, file_path: Path) -> str | None:
        """Read cached L0 sidecar if it exists and is fresh."""
        return self._read_sidecar(file_path, "l0")

    def get_l1(self, file_path: Path) -> str | None:
        """Read cached L1 sidecar if it exists and is fresh."""
        return self._read_sidecar(file_path, "l1")

    def _read_sidecar(self, file_path: Path, level: str) -> str | None:
        sidecar = self._sidecar_path(file_path, level)
        if not sidecar.exists():
            return None
        key = str(file_path.relative_to(self._store_dir))
        state = self._state.get(key)
        if state is None:
            return None
        try:
            current = file_path.read_text(errors="replace")
        except OSError:
            return None
        if state.get("hash") != content_hash(current):
            return None
        try:
            return sidecar.read_text(encoding="utf-8")
        except OSError:
            return None

    def is_fresh(self, file_path: Path, text: str) -> bool:
        """Check if existing sidecars are still valid for this content."""
        key = str(file_path.relative_to(self._store_dir))
        state = self._state.get(key)
        if state is None:
            return False
        return state.get("hash") == content_hash(text)

    def write_sidecars(
        self,
        file_path: Path,
        text: str,
        l0: str | None,
        l1: str | None,
    ) -> None:
        """Persist L0/L1 sidecar files and update state."""
        key = str(file_path.relative_to(self._store_dir))

        if l0 is not None:
            p = self._sidecar_path(file_path, "l0")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(l0, encoding="utf-8")

        if l1 is not None:
            p = self._sidecar_path(file_path, "l1")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(l1, encoding="utf-8")

        self._state[key] = {"hash": content_hash(text)}
        self._save_state()


class CacheSidecarManager:
    """Manages L0/L1 cache for external backends (Solr/Confluence).

    Uses a flat cache directory keyed by document ID since there's no
    local file to place sidecars alongside.
    """

    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def get_l0(self, doc_id: str) -> str | None:
        return self._read(doc_id, "l0")

    def get_l1(self, doc_id: str) -> str | None:
        return self._read(doc_id, "l1")

    def _path(self, doc_id: str, level: str) -> Path:
        return self._dir / f"{cache_key(doc_id)}.{level}"

    def _read(self, doc_id: str, level: str) -> str | None:
        path = self._path(doc_id, level)
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                return None
        return None

    def write(self, doc_id: str, l0: str | None, l1: str | None) -> None:
        if l0 is not None:
            p = self._path(doc_id, "l0")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(l0, encoding="utf-8")
        if l1 is not None:
            p = self._path(doc_id, "l1")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(l1, encoding="utf-8")

    def has_cache(self, doc_id: str) -> bool:
        return self._path(doc_id, "l0").exists() or self._path(
            doc_id, "l1"
        ).exists()
