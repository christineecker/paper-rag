"""PDF-only figure extraction: saves PictureItem images to papers/<doc_key>/figures/fig_N.png."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from docling_core.types.doc.document import DoclingDocument

_FIG_NUM_RE = re.compile(r"^Fig(?:ure)?\.?\s*(\d+)\s*[|:.]", re.IGNORECASE | re.MULTILINE)


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


def _captions_from_pdf_text(source_path: Optional[Path]) -> list[tuple[int, str]]:
    """List of (page_no, caption_text), scanned from the PDF's raw per-page text
    layer via pypdfium2 (1-indexed pages, matching docling's PictureItem.prov
    page_no). Not all captions survive docling's layout/reading-order
    reconstruction into `doc.texts` -- e.g. a caption block overlapping a
    multi-panel figure can be dropped entirely rather than merely mislinked -- so
    this scans the PDF directly instead of relying on docling's parsed document.
    """
    if source_path is None or source_path.suffix.lower() != ".pdf":
        return []
    try:
        import pypdfium2 as pdfium

        items: list[tuple[int, str]] = []
        pdf = pdfium.PdfDocument(source_path)
        try:
            for i, page in enumerate(pdf):
                text = page.get_textpage().get_text_range()
                for match in _FIG_NUM_RE.finditer(text):
                    tail = text[match.start() : match.start() + 500]
                    caption = re.split(r"\n\s*\n", tail, maxsplit=1)[0].replace("\n", " ").strip()
                    items.append((i + 1, caption))
        finally:
            pdf.close()
        return items
    except Exception:
        return []


def _build_caption_list(doc: DoclingDocument, source_path: Optional[Path] = None) -> list[tuple[int, str]]:
    """List of (page_no, caption_text) for every "Fig. N | ..."-style caption in
    the document, used to backfill a picture's caption when docling's own
    picture<->caption linkage picks something that isn't actually a caption.

    docling links each PictureItem to a caption by page-proximity, which misfires
    when a figure's cropped image and its caption land on different pages (a page
    break mid-figure) -- it then grabs whatever body text is nearest instead.
    Prefers scanning the source PDF's raw text directly (see
    `_captions_from_pdf_text`), since docling can drop a caption from `doc.texts`
    entirely rather than merely mislink it; falls back to `doc.texts` otherwise.
    """
    items = _captions_from_pdf_text(source_path)
    if not items:
        for item in getattr(doc, "texts", []):
            text = getattr(item, "text", None)
            if not text or not _FIG_NUM_RE.match(text.strip()):
                continue
            prov = getattr(item, "prov", None)
            page_no = getattr(prov[0], "page_no", None) if prov else None
            if page_no is not None:
                items.append((page_no, text.strip()))
    items.sort(key=lambda pair: pair[0])
    return items


def _nearest_caption(caption_list: list[tuple[int, str]], page_no: Optional[int]) -> Optional[str]:
    """The real figure caption on the page closest to `page_no`. A caption can sit
    either just before its figure (e.g. atop a multi-panel block) or right after
    (e.g. a multi-page figure whose caption trails on the next page) -- ties are
    broken toward the following page, since a caption that has visibly not yet
    appeared by `page_no` is more likely still coming than long past."""
    if page_no is None or not caption_list:
        return None
    return min(caption_list, key=lambda pair: (abs(pair[0] - page_no), 0 if pair[0] >= page_no else 1))[1]


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
    source_path: Optional[Path] = None,
    describe_figures: bool = False,
) -> list[Figure]:
    """Extract picture items with captions from a docling document (PDF sources only).

    `source_path` (the original PDF, when available) is used to backfill captions
    docling's own parse missed or mislinked -- see `_build_caption_list`.

    Uncaptioned figures are skipped by default (describe_figures opt-in is out of scope
    for the local pipeline here; a caller could wire PictureDescriptionApiOptions before
    calling this, but this function itself just filters uncaptioned figures unless asked
    to keep them)."""
    figures_dir.mkdir(parents=True, exist_ok=True)
    caption_list = _build_caption_list(doc, source_path)
    results: list[Figure] = []
    index = 0
    for picture in getattr(doc, "pictures", []):
        caption = _caption_text(doc, picture)
        page_no, bbox = _page_and_bbox(picture)

        # docling *did* link this picture to a caption item (`caption` isn't None)
        # but the text isn't actually caption-shaped ("Fig. N | ...") -- its
        # page-proximity linkage grabbed unrelated body text instead. Fall back to
        # the nearest real numbered caption in the document. A picture docling
        # never linked to any caption (`caption is None`) is left alone -- that's
        # ordinarily a non-figure image (logo, decorative background, ...).
        if caption is not None and _FIG_NUM_RE.match(caption.strip()) is None:
            fallback = _nearest_caption(caption_list, page_no)
            if fallback is not None:
                caption = fallback

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
