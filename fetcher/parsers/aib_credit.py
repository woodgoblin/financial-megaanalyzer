"""Parser for AIB credit card statements."""

import re
from pathlib import Path
from datetime import datetime

from pypdf import PdfReader

# Import Transaction model - handle both relative and absolute imports
try:
    from models import Transaction
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from models import Transaction


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

    def extract_transactions(self, pdf_path: Path) -> list[Transaction]:
        """
        Extract transaction records from an AIB credit card statement.

        Returns:
            List of Transaction objects
        """
        transactions = []
        try:
            reader = PdfReader(pdf_path)
            full_text = ""
            for page in reader.pages:
                full_text += page.extract_text() + "\n"

            # Find statement end date to determine year for transactions
            end_date = None
            end_year = None
            statement_match = re.search(
                r"Account Statement - (\d{1,2})(?:st|nd|rd|th)?\s+(\w+),\s+(\d{4})",
                full_text,
            )
            if statement_match:
                end_year = int(statement_match.group(3))
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
                month_name = statement_match.group(2)
                month_abbr = month_map.get(month_name, "Jan")
                end_date = f"{int(statement_match.group(1))} {month_abbr} {end_year}"

            # Find transaction section
            # Pattern: "Transaction Date Posting Date Details..."
            trans_start = re.search(r"Transaction\s+Date\s+Posting\s+Date", full_text)
            if not trans_start:
                return transactions

            trans_text = full_text[trans_start.end() :]
            lines = trans_text.split("\n")

            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if not line:
                    i += 1
                    continue

                # Transaction pattern: "DD MMM DD MMM <merchant> <amount>" or "<amount>CR"
                # Example: "13 Dec 15 Dec TEST SUPERMARKET   3554 TEST CITY IE 35.72"
                # Example: "5 Jan 5 Jan DIRECT DEBIT - THANK YOU 2,522.86CR"
                # Amount may have commas: "2,522.86" or "35.72"
                trans_match = re.match(
                    r"(\d{1,2})\s+(\w{3})\s+(\d{1,2})\s+(\w{3})\s+(.+?)\s+(-?\d{1,3}(?:,\d{3})*\.?\d*)(CR)?$",
                    line,
                )
                if trans_match:
                    trans_day = int(trans_match.group(1))
                    trans_month_abbr = trans_match.group(2)
                    post_day = int(trans_match.group(3))
                    post_month_abbr = trans_match.group(4)
                    details = trans_match.group(5).strip()
                    amount_str = trans_match.group(6).replace(",", "")  # Remove commas
                    amount = float(amount_str)
                    is_credit = trans_match.group(7) == "CR"  # Check for CR suffix

                    # Determine year for transaction date
                    try:
                        trans_month = datetime.strptime(trans_month_abbr, "%b").month
                        if end_date:
                            end_month = datetime.strptime(
                                end_date.split()[1], "%b"
                            ).month
                            if trans_month > end_month:
                                year = end_year - 1
                            else:
                                year = end_year
                        else:
                            year = end_year if end_year else 2025

                        transaction_date = f"{trans_day} {trans_month_abbr} {year}"
                        posting_date = f"{post_day} {post_month_abbr} {year}"
                    except (ValueError, AttributeError):
                        i += 1
                        continue

                    # Get reference number from next line(s)
                    reference = None
                    original_currency = None
                    original_amount = None
                    exchange_rate = None
                    fx_fee = None

                    i += 1
                    while i < len(lines):
                        next_line = lines[i].strip()
                        if not next_line:
                            i += 1
                            continue

                        # Check if this is a new transaction
                        if re.match(r"\d{1,2}\s+\w{3}\s+\d{1,2}\s+\w{3}", next_line):
                            break

                        # Reference number
                        ref_match = re.search(r"Ref:\s*(\d+)", next_line)
                        if ref_match:
                            reference = ref_match.group(1)
                            i += 1
                            continue

                        # Foreign currency info
                        # Format: "XX.XX USD @ rate of X.XXXXXX"
                        fx_match = re.search(
                            r"(\d+\.?\d*)\s+([A-Z]{3})\s+@\s+rate\s+of\s+(\d+\.?\d+)",
                            next_line,
                        )
                        if fx_match:
                            original_amount = float(fx_match.group(1))
                            original_currency = fx_match.group(2)
                            exchange_rate = float(fx_match.group(3))
                            i += 1
                            continue

                        # FX fee
                        fx_fee_match = re.search(
                            r"Currency Conversion Fee of\s+(\d+\.?\d+)", next_line
                        )
                        if fx_fee_match:
                            fx_fee = float(fx_fee_match.group(1))
                            i += 1
                            continue

                        # If we hit something that doesn't match, might be next transaction
                        if len(next_line) > 5 and not next_line.startswith("Ref:"):
                            break

                        i += 1

                    # Determine transaction type: CR suffix = Credit, otherwise Debit
                    transaction_type = "Credit" if is_credit else "Debit"
                    currency = original_currency if original_currency else "EUR"

                    transaction = Transaction(
                        amount=abs(amount),
                        currency=currency,
                        transaction_type=transaction_type,
                        details=details,
                        transaction_date=transaction_date,
                        reference=reference,
                        posting_date=posting_date,
                        original_currency=original_currency,
                        original_amount=original_amount,
                        exchange_rate=exchange_rate,
                        fx_fee=fx_fee,
                    )
                    transactions.append(transaction)
                else:
                    i += 1

        except Exception as e:
            # Return partial results if any
            pass

        return transactions


# Auto-register parser instance
_parser = AIBCreditParser()
from .registry import register_parser

register_parser(_parser)
