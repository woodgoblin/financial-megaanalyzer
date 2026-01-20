"""Parser for Revolut debit account statements."""

import re
from pathlib import Path
from datetime import datetime

from pypdf import PdfReader


class RevolutDebitParser:
    """Parser for Revolut debit account statements."""

    name = "Revolut Debit Account"

    def can_parse(self, pdf_text: str) -> bool:
        """Check if this is a Revolut debit account statement."""
        return (
            "EUR Statement" in pdf_text
            and ("Revolut Bank UAB" in pdf_text or "Revolut Ltd" in pdf_text)
            and "Account transactions from" in pdf_text
        )

    def extract_dates(self, pdf_path: Path) -> tuple[str, str] | None:
        """
        Extract start and end dates from a Revolut debit account statement.

        Revolut statements are consolidated and contain multiple transaction types
        (Account, Pockets, Deposit, etc.). This method extracts the FIRST and LAST
        transaction dates across all sections, regardless of transaction type.

        Transaction format: "DD MMM YYYY - DD MMM YYYY Description ..."
        We use the first date (transaction date) from each line.

        Returns:
            Tuple of (start_date, end_date) as strings in 'DD MMM YYYY' format,
            or None if dates cannot be extracted.
        """
        try:
            reader = PdfReader(pdf_path)

            # Month abbreviation to number mapping for date parsing
            month_map = {
                "Jan": 1,
                "Feb": 2,
                "Mar": 3,
                "Apr": 4,
                "May": 5,
                "Jun": 6,
                "Jul": 7,
                "Aug": 8,
                "Sep": 9,
                "Oct": 10,
                "Nov": 11,
                "Dec": 12,
            }

            # Pattern to match transaction dates: "DD MMM YYYY"
            # Transactions appear as: "DD MMM YYYY - DD MMM YYYY Description" or "DD MMM YYYY Description"
            # We match dates that are followed by either a dash+date or description text
            transaction_date_pattern = re.compile(
                r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})(?:\s+-\s+\d{1,2}\s+\w{3}\s+\d{4})?\s+[A-Z]",
                re.IGNORECASE,
            )

            all_dates = []

            for page in reader.pages:
                page_text = page.extract_text()
                if not page_text:
                    continue

                # Find all transaction dates on this page
                matches = transaction_date_pattern.finditer(page_text)
                for match in matches:
                    # Check if this date is in a header context (should be excluded)
                    match_start = match.start()
                    context_start = max(0, match_start - 50)
                    context = page_text[context_start : match_start + 20]

                    # Skip dates in headers like "Generated on [the] DD MMM YYYY", "Statement", "Page"
                    if re.search(
                        r"(Generated on|Statement|Page)(?:\s+the)?\s+\d{1,2}\s+\w{3}\s+\d{4}",
                        context,
                        re.IGNORECASE,
                    ):
                        continue

                    day = int(match.group(1))
                    month_abbr = match.group(2).capitalize()
                    year = int(match.group(3))

                    # Validate month abbreviation
                    if month_abbr in month_map:
                        # Create date tuple for sorting: (year, month, day)
                        date_tuple = (year, month_map[month_abbr], day)
                        date_str = f"{day} {month_abbr} {year}"
                        all_dates.append((date_tuple, date_str))

            if not all_dates:
                return None

            # Sort by date tuple (year, month, day)
            all_dates.sort(key=lambda x: x[0])

            # First transaction is start, last transaction is end
            start_date = all_dates[0][1]
            end_date = all_dates[-1][1]

            return (start_date, end_date)

        except Exception:
            return None


# Auto-register parser instance
_parser = RevolutDebitParser()
from .registry import register_parser

register_parser(_parser)
