"""File-based memory store — JSON files on disk."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import anyio

from semideus.core.interfaces import MemoryStore
from semideus.core.registry import registry
from semideus.core.types import ComponentType

logger = logging.getLogger(__name__)


def _sanitize_key(key: str) -> str:
    """Sanitize a key for use as a filename. Prevents path traversal."""
    # Replace path separators with underscores, strip leading dots
    sanitized = key.replace("/", "__").replace("\\", "__").lstrip(".")
    if not sanitized:
        raise ValueError(f"Invalid memory key: {key!r}")
    return sanitized


@registry.register(ComponentType.MEMORY, "file")
class FileMemoryStore(MemoryStore):
    """Stores memory entries as individual JSON files on disk.

    Directory layout:
        {base_path}/
            {sanitized_key}.json   ->  {"key", "value", "metadata", "created_at", "updated_at"}

    Supports prefix-based listing and basic keyword search over stored values.
    """

    def __init__(self, base_path: str | Path = ".semideus/memory") -> None:
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        return self._base / f"{_sanitize_key(key)}.json"

    def _read_entry(self, path: Path) -> dict[str, Any] | None:
        """Read and parse a single entry file. Returns None on failure."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Corrupt memory entry %s: %s", path, exc)
            return None

    # -- MemoryStore interface --------------------------------------------------

    async def store(
        self, key: str, value: Any, metadata: dict[str, Any] | None = None
    ) -> None:
        path = self._path_for(key)
        now = time.time()

        # Preserve created_at if the entry already exists
        existing = None
        if path.exists():
            existing = self._read_entry(path)

        entry = {
            "key": key,
            "value": value,
            "metadata": metadata or {},
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
        }

        raw = json.dumps(entry, indent=2, default=str)
        await anyio.Path(path).write_text(raw, encoding="utf-8")
        logger.debug("Stored memory: %s", key)

    async def retrieve(self, key: str) -> Any | None:
        path = self._path_for(key)
        if not path.exists():
            return None
        entry = self._read_entry(path)
        return entry["value"] if entry else None

    async def delete(self, key: str) -> bool:
        path = self._path_for(key)
        if path.exists():
            await anyio.Path(path).unlink()
            logger.debug("Deleted memory: %s", key)
            return True
        return False

    async def list_keys(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        if not self._base.exists():
            return keys
        sanitized_prefix = _sanitize_key(prefix) if prefix else ""
        for json_file in sorted(self._base.glob("*.json")):
            entry = self._read_entry(json_file)
            if entry and entry["key"].startswith(prefix):
                keys.append(entry["key"])
            elif not prefix and entry:
                keys.append(entry["key"])
        return keys

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Basic keyword search over stored values and metadata.

        Scores entries by counting occurrences of query terms in the
        serialized value and metadata.  Not semantic — use VectorMemoryStore
        for embedding-based search.
        """
        query_lower = query.lower()
        terms = query_lower.split()
        scored: list[tuple[float, dict[str, Any]]] = []

        if not self._base.exists():
            return []

        for json_file in self._base.glob("*.json"):
            entry = self._read_entry(json_file)
            if not entry:
                continue

            # Build searchable text from value + metadata
            text = json.dumps(entry["value"], default=str).lower()
            meta_text = json.dumps(entry.get("metadata", {}), default=str).lower()
            combined = f"{text} {meta_text}"

            score = sum(combined.count(term) for term in terms)
            if score > 0:
                scored.append((score, entry))

        # Sort descending by score, return top_k
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"key": e["key"], "value": e["value"], "metadata": e.get("metadata", {}), "score": s}
            for s, e in scored[:top_k]
        ]

    async def close(self) -> None:
        pass  # Nothing to clean up for file-based storage
