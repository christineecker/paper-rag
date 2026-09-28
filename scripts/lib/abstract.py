"""Abstract chunk construction (Step 3c)."""
from __future__ import annotations

from typing import Optional


def build_abstract_entry(doc_key: str, metadata: dict) -> Optional[dict]:
    """Build the single abstract chroma/bm25 entry for a paper, or None if no abstract."""
    abstract = metadata.get("abstract")
    if not abstract:
        return None
    return {
        "id": f"{doc_key}::abstract::0",
        "text": abstract,
        "type": "abstract",
        "metadata": {
            "doc_key": doc_key,
            **({"pmid": metadata["pmid"]} if metadata.get("pmid") else {}),
            **({"title": metadata["title"]} if metadata.get("title") else {}),
            "type": "abstract",
        },
    }
