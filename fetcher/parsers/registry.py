"""Parser registry with auto-detection."""

from pathlib import Path
from typing import Optional

from pypdf import PdfReader

from .base import StatementParser

_registered_parsers: list[StatementParser] = []


def register_parser(parser: StatementParser) -> None:
    """Register a statement parser for auto-detection."""
    _registered_parsers.append(parser)


def get_registered_parsers() -> list[StatementParser]:
    """Get list of all registered parsers."""
    return _registered_parsers.copy()


def parse_statement(pdf_path: Path) -> tuple[str, str, str] | None:
    """
    Auto-detect and parse statement dates from PDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Tuple of (start_date, end_date, parser_name) or None if no parser matches
    """
    try:
        reader = PdfReader(pdf_path)
        if not reader.pages:
            return None

        first_page_text = reader.pages[0].extract_text()
        if not first_page_text:
            return None

        for parser in _registered_parsers:
            if parser.can_parse(first_page_text):
                dates = parser.extract_dates(pdf_path)
                if dates:
                    return (*dates, parser.name)

        return None
    except Exception:
        return None
