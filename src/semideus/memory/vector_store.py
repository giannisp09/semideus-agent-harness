"""Vector memory store — ChromaDB-backed semantic search."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from semideus.core.interfaces import MemoryStore
from semideus.core.registry import registry
from semideus.core.types import ComponentType

logger = logging.getLogger(__name__)


@registry.register(ComponentType.MEMORY, "vector")
class VectorMemoryStore(MemoryStore):
    """Persistent memory with embedding-based semantic search via ChromaDB.

    Requires the ``vector`` optional dependency group::

        uv sync --extra vector

    Falls back gracefully if chromadb is not installed.
    """

    def __init__(
        self,
        base_path: str = ".semideus/memory/vector",
        collection_name: str = "agent_memory",
    ) -> None:
        try:
            import chromadb
        except ImportError:
            raise ImportError(
                "chromadb is required for VectorMemoryStore. "
                "Install it with: uv sync --extra vector"
            )

        self._client = chromadb.PersistentClient(path=base_path)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.debug(
            "VectorMemoryStore initialized: collection=%s, count=%d",
            collection_name,
            self._collection.count(),
        )

    # -- MemoryStore interface --------------------------------------------------

    async def store(
        self, key: str, value: Any, metadata: dict[str, Any] | None = None
    ) -> None:
        # ChromaDB expects string documents for embedding
        if isinstance(value, str):
            document = value
        else:
            document = json.dumps(value, default=str)

        chroma_meta = dict(metadata or {})
        chroma_meta["key"] = key
        chroma_meta["updated_at"] = time.time()
        # ChromaDB metadata values must be str, int, float, or bool
        chroma_meta = {
            k: v for k, v in chroma_meta.items()
            if isinstance(v, (str, int, float, bool))
        }

        self._collection.upsert(
            ids=[key],
            documents=[document],
            metadatas=[chroma_meta],
        )
        logger.debug("Vector store: upserted key=%s", key)

    async def retrieve(self, key: str) -> Any | None:
        results = self._collection.get(ids=[key], include=["documents"])
        if results["ids"]:
            docs = results["documents"]
            return docs[0] if docs else None
        return None

    async def delete(self, key: str) -> bool:
        try:
            self._collection.delete(ids=[key])
            return True
        except Exception:
            return False

    async def list_keys(self, prefix: str = "") -> list[str]:
        # ChromaDB doesn't support prefix queries natively, so we filter
        results = self._collection.get(include=[])
        all_ids = results["ids"] or []
        if prefix:
            return sorted(k for k in all_ids if k.startswith(prefix))
        return sorted(all_ids)

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic similarity search using ChromaDB embeddings."""
        if self._collection.count() == 0:
            return []

        results = self._collection.query(
            query_texts=[query],
            n_results=min(top_k, self._collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        entries: list[dict[str, Any]] = []
        ids = results["ids"][0] if results["ids"] else []
        docs = results["documents"][0] if results["documents"] else []
        metas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []

        for i, doc_id in enumerate(ids):
            entries.append({
                "key": doc_id,
                "value": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "score": 1.0 - (distances[i] if i < len(distances) else 1.0),
            })

        return entries

    async def close(self) -> None:
        pass  # ChromaDB PersistentClient handles its own cleanup
