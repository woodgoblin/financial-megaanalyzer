"""Parser for AIB credit card statements."""

import re
from pathlib import Path
from datetime import datetime

from pypdf import PdfReader


class AIBCreditParser:
    """Parser for AIB credit card statements."""

    name = "AIB Credit Card"

    def can_parse(self, pdf_text: str) -> bool:
        """Check if this is an AIB credit card statement."""
        return "Credit Limit" in pdf_text and "Account Statement" in pdf_text

    def extract_dates(self, pdf_path: Path) -> tuple[str, str] | None:
        """
        Extract start and end dates from an AIB credit card statement.

        Returns:
            Tuple of (start_date, end_date) as strings in 'DD MMM YYYY' format,
            or None if dates cannot be extracted.
        """
        try:
            reader = PdfReader(pdf_path)

            # Extract end date from last page
            end_date = None
            end_year = None

            for page in reversed(reader.pages):
                page_text = page.extract_text()
                if not page_text:
                    continue

                # Pattern: "Account Statement - 11th January, 2026"
                statement_match = re.search(
                    r"Account Statement - (\d{1,2})(?:st|nd|rd|th)?\s+(\w+),\s+(\d{4})",
                    page_text,
                )

                if statement_match:
                    day = statement_match.group(1)
                    month_name = statement_match.group(2)
                    year = statement_match.group(3)
                    end_year = int(year)

                    # Convert month name to abbreviation
                    month_map = {
                        "January": "Jan",
                        "February": "Feb",
                        "March": "Mar",
                        "April": "Apr",
                        "May": "May",
                        "June": "Jun",
                        "July": "Jul",
                        "August": "Aug",
                        "September": "Sep",
                        "October": "Oct",
                        "November": "Nov",
                        "December": "Dec",
                    }

                    month_abbr = month_map.get(month_name)
                    if month_abbr:
                        end_date = f"{int(day)} {month_abbr} {year}"
                        break

            if not end_date:
                return None

            # Extract start date from first transaction
            # Transactions format: "13 Dec 15 Dec MERCHANT NAME"
            start_date = None

            for page in reader.pages:
                page_text = page.extract_text()
                if not page_text:
                    continue

                # Look for transaction date pattern: "DD MMM DD MMM" (transaction date, posting date)
                # We want the first transaction date
                transaction_pattern = r"(\d{1,2})\s+(\w{3})\s+\d{1,2}\s+\w{3}\s+[A-Z]"

                matches = list(re.finditer(transaction_pattern, page_text))
                if matches:
                    first_match = matches[0]
                    day = first_match.group(1)
                    month_abbr = first_match.group(2)

                    # Determine year: if month is after statement month, it's previous year
                    # Otherwise same year as statement
                    try:
                        trans_month = datetime.strptime(month_abbr, "%b").month
                        end_month = datetime.strptime(end_date.split()[1], "%b").month

                        if trans_month > end_month:
                            year = end_year - 1
                        else:
                            year = end_year

                        start_date = f"{int(day)} {month_abbr} {year}"
                        break
                    except ValueError:
                        continue

            # If no transaction found, use end date as start
            if not start_date:
                start_date = end_date

            return (start_date, end_date)

        except Exception:
            return None


# Auto-register parser instance
_parser = AIBCreditParser()
from .registry import register_parser

register_parser(_parser)
