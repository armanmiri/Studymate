"""Render study guide text as PDF documents."""

from __future__ import annotations

import io
import re
from html import escape
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate


def _styles() -> dict[str, ParagraphStyle]:
    """Create paragraph styles used by generated study guides."""
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "CustomTitle", parent=styles["Title"], fontSize=24, spaceAfter=30, leading=30
        ),
        "heading1": ParagraphStyle(
            "CustomHeading1",
            parent=styles["Heading1"],
            fontSize=18,
            spaceAfter=16,
            spaceBefore=16,
            leading=22,
        ),
        "heading2": ParagraphStyle(
            "CustomHeading2",
            parent=styles["Heading2"],
            fontSize=16,
            spaceAfter=14,
            spaceBefore=14,
            leading=20,
        ),
        "normal": ParagraphStyle(
            "CustomNormal", parent=styles["Normal"], fontSize=12, spaceAfter=12, leading=14
        ),
        "bullet": ParagraphStyle(
            "CustomBullet",
            parent=styles["Normal"],
            fontSize=12,
            spaceAfter=12,
            leading=14,
            leftIndent=20,
            bulletIndent=10,
        ),
    }


def _clean_markup(line: str) -> str:
    """Remove Markdown emphasis and code delimiters from one line."""
    return line.replace("`", "").replace("*", "").replace("_", "").strip()


def _append_line(
    story: list[Any],
    raw_line: str,
    styles: dict[str, ParagraphStyle],
    in_list: bool,
) -> bool:
    """Convert one source line to a styled paragraph and return list state.

    Args:
        story: Paragraphs accumulated for the PDF.
        raw_line: Original line of guide text.
        styles: Paragraph styles from ``_styles``.
        in_list: Whether the previous line was a list item.

    Returns:
        Whether the current line continues a list.
    """
    line = raw_line.strip()
    if not line:
        story.append(Paragraph("<br/>", styles["normal"]))
        return in_list

    if line.startswith("### "):
        story.append(Paragraph(escape(_clean_markup(line[4:])), styles["heading2"]))
    elif line.startswith("## "):
        story.append(Paragraph(escape(_clean_markup(line[3:])), styles["heading1"]))
    elif line.startswith("# "):
        story.append(Paragraph(escape(_clean_markup(line[2:])), styles["title"]))
    elif line.startswith(("- ", "• ", "* ")):
        story.append(Paragraph(f"• {escape(_clean_markup(line[2:]))}", styles["bullet"]))
        return True
    elif match := re.match(r"^(\d+)\.\s+(.+)$", line):
        story.append(
            Paragraph(
                f"{match.group(1)}. {escape(_clean_markup(match.group(2)))}", styles["bullet"]
            )
        )
        return True
    else:
        if in_list:
            story.append(Paragraph("<br/>", styles["normal"]))
        story.append(Paragraph(escape(_clean_markup(line)), styles["normal"]))
    return False


def generate_pdf_from_content(content: str) -> bytes:
    """Render guide text into a formatted PDF.

    Args:
        content: Markdown-like study guide text.

    Returns:
        Generated PDF document bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72
    )
    styles = _styles()
    story: list[Any] = []
    in_list = False
    for line in content.splitlines():
        in_list = _append_line(story, line, styles, in_list)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
