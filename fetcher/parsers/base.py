"""Base protocol for statement parsers."""

from pathlib import Path
from typing import Protocol


class StatementParser(Protocol):
    """Protocol for PDF statement parsers."""

    name: str
    """Human-readable name of the parser (e.g., 'AIB Debit Account')."""

    def can_parse(self, pdf_text: str) -> bool:
        """
        Check if this parser can handle the given PDF text.

        Args:
            pdf_text: Text extracted from first page of PDF

        Returns:
            True if this parser can extract dates from this PDF format
        """
        ...

    def extract_dates(self, pdf_path: Path) -> tuple[str, str] | None:
        """
        Extract start and end dates from a PDF statement.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Tuple of (start_date, end_date) as strings, or None if extraction fails
        """
        ...
