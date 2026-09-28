"""Document conversion via docling."""
from __future__ import annotations

from pathlib import Path

from docling.backend.xml.jats_backend import Citation, JatsDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.document import DoclingDocument
from lxml import etree

SUFFIX_TO_FORMAT = {
    ".xml": InputFormat.XML_JATS,
    ".pdf": InputFormat.PDF,
    ".html": InputFormat.HTML,
    ".htm": InputFormat.HTML,
}


def _text(node: "etree._Element | None") -> str:
    """``node.text`` as a str, treating missing/empty elements as ''."""
    return (node.text or "").replace("\n", " ").strip() if node is not None else ""


def _patched_parse_element_citation(self: JatsDocumentBackend, node: "etree._Element") -> str:
    """Null-safe reimplementation of ``JatsDocumentBackend._parse_element_citation``.

    Real-world JATS XML (e.g. NCBI efetch output) has `<element-citation>` nodes
    where `<name>`, `<article-title>`, `<source>`, `<pub-id>`, etc. can be present
    but empty (no text content) -- upstream docling calls ``.text.replace(...)``
    directly and crashes with AttributeError on those. This mirrors upstream's
    logic field-for-field but goes through `_text()` everywhere.
    """
    citation: Citation = {
        "author_names": "",
        "title": "",
        "source": "",
        "year": "",
        "volume": "",
        "page": "",
        "pub_id": "",
        "publisher_name": "",
        "publisher_loc": "",
    }

    names = []
    for name_node in node.xpath(".//name"):
        surname_nodes = name_node.xpath("surname")
        given_nodes = name_node.xpath("given-names")
        surname = _text(surname_nodes[0]) if surname_nodes else ""
        given = _text(given_nodes[0]) if given_nodes else ""
        name_str = (surname + " " + given).strip()
        if name_str:
            names.append(name_str)
    etal_node = node.xpath(".//etal")
    if len(etal_node) > 0:
        etal_text = etal_node[0].text or "et al."
        names.append(etal_text)
    citation["author_names"] = ", ".join(names)

    titles: list[str] = [
        "article-title",
        "chapter-title",
        "data-title",
        "issue-title",
        "part-title",
        "trans-title",
    ]
    title_node: "etree._Element | None" = None
    for name in titles:
        name_node = node.xpath(name)
        if len(name_node) > 0:
            title_node = name_node[0]
            break
    citation["title"] = (
        JatsDocumentBackend._get_text(title_node) if title_node is not None else _text(node)
    )

    fields: list[str] = ["source", "year", "publisher-name", "publisher-loc", "volume"]
    for item in fields:
        item_node = node.xpath(item)
        if len(item_node) > 0:
            citation[item.replace("-", "_")] = _text(item_node[0])  # type: ignore[literal-required]

    if len(node.xpath("pub-id")) > 0:
        pub_id: list[str] = []
        for id_node in node.xpath("pub-id"):
            id_type = id_node.get("assigning-authority") or id_node.get("pub-id-type")
            id_text = id_node.text
            if id_type and id_text:
                pub_id.append(id_type.replace("\n", " ").strip().upper() + ": " + id_text.replace("\n", " ").strip())
        if pub_id:
            citation["pub_id"] = ", ".join(pub_id)

    if len(node.xpath("elocation-id")) > 0:
        citation["page"] = _text(node.xpath("elocation-id")[0])
    elif len(node.xpath("fpage")) > 0:
        citation["page"] = _text(node.xpath("fpage")[0])
        if len(node.xpath("lpage")) > 0:
            citation["page"] += "–" + _text(node.xpath("lpage")[0])  # noqa: RUF001

    text = ""
    if citation["author_names"]:
        text += citation["author_names"].rstrip(".") + ". "
    if citation["title"]:
        text += citation["title"] + ". "
    if citation["source"]:
        text += citation["source"] + ". "
    if citation["publisher_name"]:
        if citation["publisher_loc"]:
            text += f"{citation['publisher_loc']}: "
        text += citation["publisher_name"] + ". "
    if citation["volume"]:
        text = text.rstrip(". ")
        text += f" {citation['volume']}. "
    if citation["page"]:
        text = text.rstrip(". ")
        if citation["volume"]:
            text += ":"
        text += citation["page"] + ". "
    if citation["year"]:
        text = text.rstrip(". ")
        text += f" ({citation['year']})."
    if citation["pub_id"]:
        text = text.rstrip(".") + ". "
        text += citation["pub_id"]

    return text


JatsDocumentBackend._parse_element_citation = _patched_parse_element_citation


def convert_document(path: Path, ocr: bool = False) -> DoclingDocument:
    """Convert a local source file (JATS XML / PDF / HTML) to a DoclingDocument."""
    pdf_options = PdfPipelineOptions(
        do_ocr=ocr,
        generate_picture_images=True,
        images_scale=2.0,
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
        }
    )
    result = converter.convert(str(path))
    return result.document
