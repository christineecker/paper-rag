"""Chunking via docling's HybridChunker, tied to the embedding model's tokenizer/max_tokens."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from docling.chunking import HybridChunker
from docling_core.types.doc.document import DoclingDocument

# Known max sequence lengths for common embedding models; falls back to 512 (a safe,
# widely-supported default) for unlisted models so we never silently over-run at embed time.
MODEL_MAX_TOKENS = {
    "BAAI/bge-small-en-v1.5": 512,
    "BAAI/bge-base-en-v1.5": 512,
    "BAAI/bge-large-en-v1.5": 512,
    "BAAI/bge-m3": 8192,
    "jinaai/jina-embeddings-v2-base-en": 8192,
}
DEFAULT_MAX_TOKENS = 512

SKIP_HEADING_RE = re.compile(
    r"^(references?|bibliography|reference list|abstract)$", re.IGNORECASE
)


@dataclass
class Chunk:
    text: str
    heading_path: Optional[str] = None
    page_no: Optional[int] = None
    type: str = "text"
    extra: dict = field(default_factory=dict)


def _max_tokens_for_model(embedding_model: str) -> int:
    return MODEL_MAX_TOKENS.get(embedding_model, DEFAULT_MAX_TOKENS)


def _build_tokenizer(embedding_model: str, max_tokens: int):
    """Build a docling-compatible tokenizer for the given embedding model."""
    try:
        from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
        from transformers import AutoTokenizer

        hf_tokenizer = AutoTokenizer.from_pretrained(embedding_model)
        return HuggingFaceTokenizer(tokenizer=hf_tokenizer, max_tokens=max_tokens)
    except Exception:
        # Older/newer docling versions may accept a plain model name string instead.
        return None


def _heading_path_str(chunk) -> str:
    meta = getattr(chunk, "meta", None)
    headings = getattr(meta, "headings", None) if meta else None
    if not headings:
        return ""
    return " > ".join(h for h in headings if h)


def _is_skipped_section(heading_path: str) -> bool:
    if not heading_path:
        return False
    for part in heading_path.split(" > "):
        if SKIP_HEADING_RE.match(part.strip()):
            return True
    return False


def _is_picture_chunk(chunk) -> bool:
    meta = getattr(chunk, "meta", None)
    doc_items = getattr(meta, "doc_items", None) if meta else None
    if not doc_items:
        return False
    for item in doc_items:
        label = getattr(item, "label", None)
        label_value = getattr(label, "value", label)
        if label_value and str(label_value).lower() in ("picture", "caption"):
            return True
    return False


def _page_no(chunk) -> Optional[int]:
    meta = getattr(chunk, "meta", None)
    doc_items = getattr(meta, "doc_items", None) if meta else None
    if not doc_items:
        return None
    for item in doc_items:
        prov = getattr(item, "prov", None)
        if prov:
            for p in prov:
                page_no = getattr(p, "page_no", None)
                if page_no is not None:
                    return page_no
    return None


def chunk_document(doc: DoclingDocument, embedding_model: str) -> list[Chunk]:
    """Chunk a DoclingDocument with HybridChunker, skipping ref-list, abstract, and
    figure/caption nodes (see plan Step 3 for rationale)."""
    max_tokens = _max_tokens_for_model(embedding_model)
    tokenizer = _build_tokenizer(embedding_model, max_tokens)

    chunker_kwargs = {}
    if tokenizer is not None:
        chunker_kwargs["tokenizer"] = tokenizer
    else:
        chunker_kwargs["max_tokens"] = max_tokens

    chunker = HybridChunker(**chunker_kwargs)

    results: list[Chunk] = []
    for raw_chunk in chunker.chunk(doc):
        heading_path = _heading_path_str(raw_chunk)
        if _is_skipped_section(heading_path):
            continue
        if _is_picture_chunk(raw_chunk):
            continue
        text = chunker.contextualize(raw_chunk) if hasattr(chunker, "contextualize") else raw_chunk.text
        if not text or not text.strip():
            continue
        results.append(
            Chunk(
                text=text,
                heading_path=heading_path or None,
                page_no=_page_no(raw_chunk),
                type="text",
            )
        )
    return results
