"""Document conversion via docling."""
from __future__ import annotations

from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.document import DoclingDocument

SUFFIX_TO_FORMAT = {
    ".xml": InputFormat.XML_JATS,
    ".pdf": InputFormat.PDF,
    ".html": InputFormat.HTML,
    ".htm": InputFormat.HTML,
}


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
