"""Extract text from uploaded documents supported by StudyMate."""

from __future__ import annotations

import io
import logging
from typing import Callable

import pandas as pd
import PyPDF2
import pytesseract
import textract
from docx import Document
from PIL import Image
from pptx import Presentation

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = frozenset(
    {".txt", ".md", ".py", ".js", ".html", ".css", ".json", ".csv", ".log", ".xml", ".yaml", ".yml"}
)
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"})


class DocumentProcessingError(ValueError):
    """Identify an upload that could not be decoded into text."""


def _extract_text(data: bytes) -> str:
    """Decode a text-based upload using common encodings."""
    for encoding in ("utf-8", "latin-1", "ascii", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentProcessingError("Could not decode file content as text.")


def _extract_pdf(data: bytes) -> str:
    """Extract text from all pages of a PDF upload."""
    reader = PyPDF2.PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_word(data: bytes) -> str:
    """Extract paragraph text from a Word document."""
    document = Document(io.BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _extract_spreadsheet(data: bytes) -> str:
    """Render spreadsheet rows as plain text."""
    frame = pd.read_excel(io.BytesIO(data))
    return frame.to_string(index=False)


def _extract_powerpoint(data: bytes) -> str:
    """Extract text from shapes in a PowerPoint presentation."""
    presentation = Presentation(io.BytesIO(data))
    return "\n".join(
        shape.text
        for slide in presentation.slides
        for shape in slide.shapes
        if hasattr(shape, "text")
    )


def _extract_image(data: bytes) -> str:
    """Use OCR to extract text from an image upload."""
    with Image.open(io.BytesIO(data)) as image:
        if image.mode in {"RGBA", "P"}:
            image = image.convert("RGB")
        text = pytesseract.image_to_string(image)
    if not text.strip():
        raise DocumentProcessingError("No readable text was found in the image.")
    return text


def _extract_fallback(data: bytes, extension: str) -> str:
    """Use textract for formats without a dedicated handler."""
    return textract.process(io.BytesIO(data), extension=extension.lstrip(".")).decode("utf-8")


def extract_document_text(data: bytes, extension: str) -> str:
    """Extract text from an uploaded file based on its lowercase extension.

    Args:
        data: Raw file bytes.
        extension: Lowercase file extension, including the leading dot.

    Returns:
        Extracted text.

    Raises:
        DocumentProcessingError: If the format is unsupported or extraction fails.
    """
    extractors: dict[str, Callable[[bytes], str]] = {
        ".pdf": _extract_pdf,
        ".doc": _extract_word,
        ".docx": _extract_word,
        ".xlsx": _extract_spreadsheet,
        ".xls": _extract_spreadsheet,
        ".pptx": _extract_powerpoint,
    }
    if extension in TEXT_EXTENSIONS:
        return _extract_text(data)
    if extension in IMAGE_EXTENSIONS:
        return _extract_image(data)
    if not extension:
        raise DocumentProcessingError(f"Unsupported file type: {extension or '(none)'}")
    try:
        if extension in extractors:
            return extractors[extension](data)
        return _extract_fallback(data, extension)
    except DocumentProcessingError:
        raise
    except Exception as exc:
        logger.warning("Document extraction failed for %s: %s", extension, exc)
        raise DocumentProcessingError(f"Could not extract text from {extension} file.") from exc
