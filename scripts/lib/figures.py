"""PDF-only figure extraction: saves PictureItem images to papers/<doc_key>/figures/fig_N.png."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from docling_core.types.doc.document import DoclingDocument


@dataclass
class Figure:
    index: int
    path: Path
    caption: Optional[str]
    page_no: Optional[int]
    bbox: Optional[dict]


def _caption_text(doc: DoclingDocument, picture) -> Optional[str]:
    get_caption = getattr(picture, "caption_text", None)
    if callable(get_caption):
        try:
            text = get_caption(doc)
            if text:
                return text.strip()
        except Exception:
            pass
    captions = getattr(picture, "captions", None)
    if captions:
        parts = []
        for cap_ref in captions:
            try:
                cap_item = cap_ref.resolve(doc)
                text = getattr(cap_item, "text", None)
                if text:
                    parts.append(text)
            except Exception:
                continue
        if parts:
            return " ".join(parts).strip()
    return None


def _page_and_bbox(picture) -> tuple[Optional[int], Optional[dict]]:
    prov = getattr(picture, "prov", None)
    if not prov:
        return None, None
    p = prov[0]
    page_no = getattr(p, "page_no", None)
    bbox_obj = getattr(p, "bbox", None)
    bbox = None
    if bbox_obj is not None:
        bbox = {
            "l": getattr(bbox_obj, "l", None),
            "t": getattr(bbox_obj, "t", None),
            "r": getattr(bbox_obj, "r", None),
            "b": getattr(bbox_obj, "b", None),
        }
    return page_no, bbox


def extract_figures(
    doc: DoclingDocument,
    doc_key: str,
    figures_dir: Path,
    describe_figures: bool = False,
) -> list[Figure]:
    """Extract picture items with captions from a docling document (PDF sources only).

    Uncaptioned figures are skipped by default (describe_figures opt-in is out of scope
    for the local pipeline here; a caller could wire PictureDescriptionApiOptions before
    calling this, but this function itself just filters uncaptioned figures unless asked
    to keep them)."""
    figures_dir.mkdir(parents=True, exist_ok=True)
    results: list[Figure] = []
    index = 0
    for picture in getattr(doc, "pictures", []):
        caption = _caption_text(doc, picture)
        if caption is None and not describe_figures:
            continue

        image = None
        get_image = getattr(picture, "get_image", None)
        if callable(get_image):
            try:
                image = get_image(doc)
            except Exception:
                image = None
        if image is None:
            continue

        page_no, bbox = _page_and_bbox(picture)
        out_path = figures_dir / f"fig_{index}.png"
        image.save(out_path, format="PNG")

        results.append(
            Figure(
                index=index,
                path=out_path,
                caption=caption,
                page_no=page_no,
                bbox=bbox,
            )
        )
        index += 1
    return results


def bbox_to_json(bbox: Optional[dict]) -> Optional[str]:
    if bbox is None:
        return None
    return json.dumps(bbox)
