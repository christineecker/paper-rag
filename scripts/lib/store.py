"""Chroma persistent store wrapper (Step 4)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

SCALAR_TYPES = (str, int, float, bool)


def sanitize_metadata(metadata: dict) -> dict:
    """Enforce scalar-only metadata values; omit keys with no value (never store None)."""
    clean = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, SCALAR_TYPES):
            clean[key] = value
        elif isinstance(value, (list, tuple)):
            if not value:
                continue
            clean[key] = ", ".join(str(v) for v in value)
        else:
            clean[key] = str(value)
    return clean


def get_client(chroma_path: Path) -> chromadb.ClientAPI:
    chroma_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(chroma_path))


def get_collection(chroma_path: Path, embedding_model: str, collection_name: str):
    client = get_client(chroma_path)
    embedding_function = SentenceTransformerEmbeddingFunction(model_name=embedding_model)
    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine", "embedding_model": embedding_model},
    )
    return collection


def collection_exists(chroma_path: Path, collection_name: str) -> bool:
    client = get_client(chroma_path)
    existing = [c.name for c in client.list_collections()]
    return collection_name in existing


def list_collections(chroma_path: Path) -> list[str]:
    client = get_client(chroma_path)
    return [c.name for c in client.list_collections()]


def upsert_chunks(collection, entries: list[dict]) -> None:
    """entries: [{id, text, metadata}, ...] — metadata sanitized to scalars here."""
    if not entries:
        return
    ids = [e["id"] for e in entries]
    documents = [e["text"] for e in entries]
    metadatas = [sanitize_metadata(e["metadata"]) for e in entries]
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)


def delete_by_doc_key(collection, doc_key: str) -> None:
    collection.delete(where={"doc_key": doc_key})


def query_collection(collection, question: str, k: int = 5, where: Optional[dict] = None):
    query_kwargs = {"query_texts": [question], "n_results": k}
    if where:
        query_kwargs["where"] = where
    return collection.query(**query_kwargs)
