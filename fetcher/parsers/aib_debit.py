"""Parser for AIB debit account statements."""

import logging
import re
from pathlib import Path

from pypdf import PdfReader
import pdfplumber

logger = logging.getLogger(__name__)

# Import Transaction model - handle both relative and absolute imports
try:
    from models import Transaction
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from models import Transaction


# Constants for transaction parsing
MIN_BALANCE_VALUE = 0.01
MAX_TRANSACTION_AMOUNT = 1_000_000.0
MIN_TRANSACTION_AMOUNT = 0.01
MAX_LOOKAHEAD_LINES = 15
MAX_DETAILS_LENGTH = 100
HEADER_TOLERANCE_Y = 5


class AIBDebitParser:
    """Parser for AIB Personal Bank Account (debit) statements."""

    name = "AIB Debit Account"

    def can_parse(self, pdf_text: str) -> bool:
        """Check if this is an AIB debit account statement."""
        return (
            "Statement of Account" in pdf_text
            and "Personal Bank Account" in pdf_text
            and "Date of Statement" in pdf_text
        )

    def extract_dates(self, pdf_path: Path) -> tuple[str, str] | None:
        """
        Extract start and end dates from an AIB debit account statement.

        Uses a two-strategy approach:
        1. Primary: Look for "BALANCE FORWARD" date (true statement start)
        2. Fallback: Look for first transaction date

        Returns:
            Tuple of (start_date, end_date) as strings in 'DD MMM YYYY' format,
            or None if dates cannot be extracted.
        """
        try:
            reader = PdfReader(pdf_path)

            # Extract end date from last non-empty page
            end_date = None
            for page in reversed(reader.pages):
                page_text = page.extract_text()
                if not page_text or len(page_text.strip()) < 50:
                    continue

                statement_date_match = re.search(
                    r"Date of Statement\s+(\d{1,2}\s+\w{3}\s+\d{4})", page_text
                )

                if statement_date_match:
                    end_date = statement_date_match.group(1)
                    break

            if not end_date:
                return None

            # Extract start date using two-strategy approach
            start_date = None

            # STRATEGY 1: Look for BALANCE FORWARD date (primary method)
            balance_forward_pattern = r"(\d{1,2}\s+\w{3}\s+\d{4})\s+BALANCE FORWARD"

            for page in reader.pages:
                page_text = page.extract_text()
                if not page_text:
                    continue

                balance_forward_match = re.search(balance_forward_pattern, page_text)
                if balance_forward_match:
                    start_date = balance_forward_match.group(1)
                    break

            # STRATEGY 2: Fallback to first transaction date
            if not start_date:
                date_pattern = r"(\d{1,2}\s+\w{3}\s+\d{4})"

                for page in reader.pages:
                    page_text = page.extract_text()
                    if not page_text:
                        continue

                    matches = re.finditer(date_pattern, page_text)
                    for match in matches:
                        candidate_date = match.group(1)
                        line_context = page_text[
                            max(0, match.start() - 50) : match.end() + 150
                        ]

                        if "Date of Statement" in line_context:
                            continue
                        if (
                            "Date Details" in line_context
                            and "Debit" not in line_context
                        ):
                            continue

                        start_date = candidate_date
                        break

                    if start_date:
                        break

            # Last resort: use end date as start date
            if not start_date:
                start_date = end_date

            return (start_date, end_date)

        except Exception as e:
            logger.error(
                f"Error extracting dates from {pdf_path.name}: {e}", exc_info=True
            )
            return None

    def extract_transactions(self, pdf_path: Path) -> list[Transaction]:
        """
        Extract transaction records from an AIB debit account statement.

        Uses column-based detection: determines debit/credit by which column
        the amount appears in, not by keywords.

        Returns:
            List of Transaction objects
        """
        transactions = []
        try:
            # Use pdfplumber to extract words with positions
            with pdfplumber.open(pdf_path) as pdf:
                # Step 1: Identify column boundaries from header
                column_bounds = self._identify_columns(pdf)
                if not column_bounds:
                    # Column detection failed - cannot extract transactions
                    return []

                # Step 2: Extract transactions using column positions
                transactions = self._extract_transactions_by_columns(pdf, column_bounds)

        except Exception as e:
            # Log error but return empty list rather than crashing
            logger.error(
                f"Error extracting transactions from {pdf_path.name}: {e}",
                exc_info=True,
            )
            return []

        return transactions

    def _identify_columns(self, pdf) -> dict | None:
        """
        Identify column boundaries by finding the header row.

        Returns:
            Dictionary with column x-coordinate ranges, or None if not found
        """
        for page in pdf.pages:
            words = page.extract_words()

            # Find header row - look for "Debit" and "Credit" keywords
            debit_header = None
            credit_header = None
            balance_header = None

            for word in words:
                text = word["text"].upper()
                x_center = (word["x0"] + word["x1"]) / 2

                if text == "DEBIT" or (
                    text.startswith("DEBIT") and "€" in word.get("text", "")
                ):
                    debit_header = word
                elif text == "CREDIT" or (
                    text.startswith("CREDIT") and "€" in word.get("text", "")
                ):
                    credit_header = word
                elif text == "BALANCE" or (
                    text.startswith("BALANCE") and "€" in word.get("text", "")
                ):
                    balance_header = word

            if debit_header and credit_header:
                # Define column ranges based on actual observed positions
                # Debit amounts appear around x=290-300
                # Credit amounts appear around x=348-352
                # Balance amounts appear around x=410+

                # Use wider ranges to catch all variations
                debit_x_min = debit_header["x0"] - 50  # Start well before
                debit_x_max = credit_header["x0"] - 5  # End before credit starts

                credit_x_min = credit_header["x0"] - 10
                credit_x_max = credit_header["x1"] + 20

                balance_x_min = credit_header["x1"] + 50
                balance_x_max = 1000  # Large number

                return {
                    "debit": (debit_x_min, debit_x_max),
                    "credit": (credit_x_min, credit_x_max),
                    "balance": (balance_x_min, balance_x_max),
                    "header_y": debit_header["top"],
                }

        return None

    def _extract_date_from_line(
        self, line_words: list, date_pattern: re.Pattern
    ) -> str | None:
        """Extract date from line words. Handles dates split across multiple words."""
        if not line_words:
            return None

        # Try single word match first
        text = line_words[0]["text"]
        date_match = date_pattern.match(text)
        if date_match:
            return date_match.group(1)

        # Try combining first 3 words (for "15 Sep 2025")
        if len(line_words) >= 3:
            combined = f"{line_words[0]['text']} {line_words[1]['text']} {line_words[2]['text']}"
            date_match = date_pattern.match(combined)
            if date_match:
                return date_match.group(1)

        return None

    def _process_opening_balance_line(
        self,
        line_words: list,
        line_text: str,
        balance_range: tuple,
        date_pattern: re.Pattern,
    ) -> tuple[dict | None, str | None]:
        """
        Process a BALANCE FORWARD or OPENING BALANCE line.

        Returns:
            Tuple of (opening_balance_dict, extracted_date) or (None, None)
        """
        # Extract date from this line if present
        extracted_date = self._extract_date_from_line(line_words, date_pattern)

        # Extract balance from balance column
        opening_balance = None
        for word in line_words:
            x_center = (word.get("x0", 0) + word.get("x1", 0)) / 2
            if balance_range[0] <= x_center <= balance_range[1]:
                try:
                    opening_balance = float(word["text"].replace(",", ""))
                except ValueError:
                    pass

        if opening_balance is None:
            return None, extracted_date

        return {
            "amount": 0.0,
            "balance": opening_balance,
            "details": (
                "OPENING BALANCE"
                if "OPENING" in line_text.upper()
                else "BALANCE FORWARD"
            ),
            "date": extracted_date,
        }, extracted_date

    def _find_transaction_amounts(
        self,
        line_words: list,
        debit_range: tuple,
        credit_range: tuple,
        balance_range: tuple,
    ) -> tuple[list, float | None, str | None]:
        """
        Find transaction amounts, balance, and reference on a line.

        Returns:
            Tuple of (tx_amounts_list, balance_value, reference_value)
        """
        tx_amounts = []
        balance_value = None
        reference_value = None

        for word in line_words:
            text = word["text"].replace(",", "")
            x_center = (word.get("x0", 0) + word.get("x1", 0)) / 2

            # Check for balance in balance column
            if balance_range[0] <= x_center <= balance_range[1]:
                try:
                    val = float(text)
                    if MIN_BALANCE_VALUE < val < MAX_TRANSACTION_AMOUNT:
                        balance_value = val
                except ValueError:
                    pass

            # Check for reference
            if text.startswith("IE") and len(text) > 10:
                reference_value = text

            # Check for transaction amount
            if re.match(r"^\d+\.?\d{1,2}$", text):
                try:
                    amount = float(text)
                    if MIN_TRANSACTION_AMOUNT <= amount <= MAX_TRANSACTION_AMOUNT:
                        if debit_range[0] <= x_center <= debit_range[1]:
                            tx_amounts.append(("debit", amount, word))
                        elif credit_range[0] <= x_center <= credit_range[1]:
                            tx_amounts.append(("credit", amount, word))
                except ValueError:
                    pass

        return tx_amounts, balance_value, reference_value

    def _collect_transaction_details(
        self,
        line_words: list,
        amount_word: dict,
        current_date: str,
        date_pattern: re.Pattern,
        debit_range: tuple,
    ) -> str:
        """Collect transaction description from words before the amount."""
        details_max_x = debit_range[0]  # Details column ends before debit column

        desc_words = [
            w
            for w in line_words
            if w.get("x0", 0) < amount_word.get("x0", 0)
            and w.get("x0", 0) < details_max_x
            and not date_pattern.match(w["text"])
            and w["text"] != current_date.split()[0]  # Exclude day number
            and w["text"] != current_date.split()[1]  # Exclude month
            and w["text"] != current_date.split()[2]  # Exclude year
        ]
        return " ".join(w["text"] for w in desc_words).strip()

    def _collect_additional_info_from_lines(
        self,
        start_idx: int,
        sorted_y: list,
        lines: dict,
        date_pattern: re.Pattern,
        debit_range: tuple,
        credit_range: tuple,
        balance_range: tuple,
        footer_keywords: list,
        details_max_x: float,
        initial_reference: str | None,
        initial_balance: float | None,
    ) -> dict:
        """
        Look ahead through following lines to collect reference, FX info, balance, and additional details.

        Returns:
            Dictionary with keys: reference, balance, fx_info, details_extension
        """
        result = {
            "reference": initial_reference,
            "balance": initial_balance,
            "fx_info": {},
            "details_extension": "",
        }

        for j in range(
            start_idx + 1, min(start_idx + MAX_LOOKAHEAD_LINES, len(sorted_y))
        ):
            next_y = sorted_y[j]
            next_line_words = sorted(lines[next_y], key=lambda w: w.get("x0", 0))
            next_line_text = " ".join(w["text"] for w in next_line_words)

            # Stop if we hit another date
            if next_line_words and date_pattern.match(next_line_words[0]["text"]):
                break

            # Stop if we hit another transaction amount
            has_another_tx = False
            for word in next_line_words:
                text = word["text"].replace(",", "")
                if re.match(r"^\d+\.?\d{1,2}$", text):
                    try:
                        amt = float(text)
                        if MIN_TRANSACTION_AMOUNT <= amt <= MAX_TRANSACTION_AMOUNT:
                            x_center = (word.get("x0", 0) + word.get("x1", 0)) / 2
                            if (
                                debit_range[0] <= x_center <= debit_range[1]
                                or credit_range[0] <= x_center <= credit_range[1]
                            ):
                                has_another_tx = True
                                break
                    except ValueError:
                        pass

            if has_another_tx:
                break

            # Collect reference
            if not result["reference"]:
                ref_match = re.search(r"(IE\d{12,})", next_line_text)
                if ref_match:
                    result["reference"] = ref_match.group(1)

            # Collect balance
            if not result["balance"]:
                for word in next_line_words:
                    x_center = (word.get("x0", 0) + word.get("x1", 0)) / 2
                    if balance_range[0] <= x_center <= balance_range[1]:
                        try:
                            val = float(word["text"].replace(",", ""))
                            if val > MIN_BALANCE_VALUE:
                                result["balance"] = val
                                break
                        except ValueError:
                            pass

            # Collect FX info
            if "original_currency" not in result["fx_info"]:
                fx_match = re.search(
                    r"(\d+\.?\d*)\s+([A-Z]{3})@\s*(\d+\.?\d+)?", next_line_text
                )
                if fx_match:
                    result["fx_info"]["original_amount"] = float(fx_match.group(1))
                    result["fx_info"]["original_currency"] = fx_match.group(2)
                    if fx_match.group(3):
                        result["fx_info"]["exchange_rate"] = float(fx_match.group(3))
                    # Add FX info to details
                    if fx_match.group(3):
                        result[
                            "details_extension"
                        ] += f" {fx_match.group(1)} {fx_match.group(2)}@ {fx_match.group(3)}"
                    else:
                        result[
                            "details_extension"
                        ] += f" {fx_match.group(1)} {fx_match.group(2)}@"

            # Collect FX fee
            if "fx_fee" not in result["fx_info"]:
                fx_fee_match = re.search(
                    r"INCL FX FEE\s+[E€]?(\d+\.?\d+)", next_line_text
                )
                if fx_fee_match:
                    result["fx_info"]["fx_fee"] = float(fx_fee_match.group(1))
                    result[
                        "details_extension"
                    ] += " INCL FX FEE E" + fx_fee_match.group(1)

            # Check for footer - stop immediately
            if any(kw in next_line_text for kw in footer_keywords):
                break

            # Additional description (but skip numbers and duplicates)
            if not re.match(r"^\d+\.?\d+$", next_line_text.strip()):
                # Skip if it looks like a balance
                if re.search(r"\b\d{5,}\.?\d*\b", next_line_text):
                    continue

                # Filter out words beyond details column
                details_words = [
                    w for w in next_line_words if w.get("x0", 0) < details_max_x
                ]
                if not details_words:
                    continue

                clean_text = " ".join(w["text"] for w in details_words).strip()

                # Avoid duplicates and very long lines
                if clean_text and len(clean_text) < MAX_DETAILS_LENGTH:
                    if clean_text not in result["details_extension"]:
                        result["details_extension"] += " " + clean_text

        return result

    def _extract_transactions_by_columns(
        self, pdf, column_bounds: dict
    ) -> list[Transaction]:
        """
        Extract transactions using column position detection.

        Processes line by line, determining debit/credit based on which column
        the amount appears in.
        """
        transactions = []
        date_pattern = re.compile(r"^(\d{1,2}\s+\w{3}\s+\d{4})")

        debit_range = column_bounds["debit"]
        credit_range = column_bounds["credit"]
        balance_range = column_bounds["balance"]
        header_y = column_bounds["header_y"]

        # Footer keywords - stop processing when we encounter these
        footer_keywords = [
            "This is an eligible deposit",
            "Deposit Guarantee Scheme",
            "Thank you for banking",
            "Overdrawn balances are marked",
            "Allied Irish Banks",
            "Personal Bank Account",
            "Statement of Account",
            "Branch",
            "National Sort Code",
            "Telephone",
            "Page Number",
            "Account Name",
            "Account Number",
            "Date of Statement",
            "IBAN:",
            "Authorised Limit",
            "Date Details Debit",
            "www.aib.ie",
            "standardconditions",
            "ForImportantInformation",
            "For Important Information",
            "YourAuthorisedLimit",
            "Your Authorised Limit",
        ]

        prev_balance = None
        opening_balance_tx = (
            None  # Store opening balance transaction to insert at start
        )

        # Process each page
        for page in pdf.pages:
            words = page.extract_words()

            # Group words by line (y-coordinate)
            lines = {}
            for word in words:
                # Skip header
                if abs(word.get("top", 0) - header_y) < HEADER_TOLERANCE_Y:
                    continue
                # Skip footer
                if any(kw in word["text"] for kw in footer_keywords):
                    continue

                y_key = round(word.get("top", 0))
                if y_key not in lines:
                    lines[y_key] = []
                lines[y_key].append(word)

            # Process lines in order
            sorted_y = sorted(lines.keys())
            i = 0
            current_date = None

            while i < len(sorted_y):
                y_pos = sorted_y[i]
                line_words = sorted(lines[y_pos], key=lambda w: w.get("x0", 0))

                # Check for BALANCE FORWARD and OPENING BALANCE
                line_text = " ".join(w["text"] for w in line_words)
                if (
                    "BALANCE FORWARD" in line_text.upper()
                    or "OPENING BALANCE" in line_text.upper()
                ):
                    balance_tx, extracted_date = self._process_opening_balance_line(
                        line_words, line_text, balance_range, date_pattern
                    )
                    if balance_tx and opening_balance_tx is None:
                        opening_balance_tx = balance_tx
                        prev_balance = balance_tx["balance"]
                    if extracted_date:
                        current_date = extracted_date
                    i += 1
                    continue

                # Check if line starts with a date
                date_str = self._extract_date_from_line(line_words, date_pattern)
                if date_str:
                    current_date = date_str

                # Process transaction amounts even on continuation lines (when current_date is set)
                # This handles cases where multiple transactions on the same day don't all have dates
                if not current_date:
                    i += 1
                    continue

                # Find transaction amounts on this line
                tx_amounts, balance_value, reference_value = (
                    self._find_transaction_amounts(
                        line_words, debit_range, credit_range, balance_range
                    )
                )

                # Process each transaction amount found on this line
                for tx_type, amount, amount_word in tx_amounts:
                    # Collect description
                    details = self._collect_transaction_details(
                        line_words, amount_word, current_date, date_pattern, debit_range
                    )

                    # Look ahead for additional info (reference, FX, balance)
                    details_max_x = debit_range[0]
                    additional_info = self._collect_additional_info_from_lines(
                        i,
                        sorted_y,
                        lines,
                        date_pattern,
                        debit_range,
                        credit_range,
                        balance_range,
                        footer_keywords,
                        details_max_x,
                        reference_value,
                        balance_value,
                    )

                    # Combine details with extension
                    full_details = (
                        details + additional_info["details_extension"]
                    ).strip()

                    # Create transaction
                    transaction = Transaction(
                        amount=amount,
                        currency="EUR",
                        transaction_type="Debit" if tx_type == "debit" else "Credit",
                        details=full_details,
                        transaction_date=current_date,
                        balance=additional_info["balance"],
                        reference=additional_info["reference"],
                        original_currency=additional_info["fx_info"].get(
                            "original_currency"
                        ),
                        original_amount=additional_info["fx_info"].get(
                            "original_amount"
                        ),
                        exchange_rate=additional_info["fx_info"].get("exchange_rate"),
                        fx_fee=additional_info["fx_info"].get("fx_fee"),
                    )
                    transactions.append(transaction)

                    # Update balance
                    if additional_info["balance"] is not None:
                        prev_balance = additional_info["balance"]

                i += 1

        # Insert opening balance transaction at the beginning if we found one
        if opening_balance_tx:
            # Use first transaction date if opening balance didn't have a date
            if opening_balance_tx["date"] is None and transactions:
                opening_balance_tx["date"] = transactions[0].transaction_date

            # Create the opening balance transaction
            opening_tx = Transaction(
                amount=opening_balance_tx["amount"],
                currency="EUR",
                transaction_type="Credit",  # Opening balance is effectively a credit
                details=opening_balance_tx["details"],
                transaction_date=opening_balance_tx["date"] or "Unknown",
                balance=opening_balance_tx["balance"],
                reference=None,
                original_currency=None,
                original_amount=None,
                exchange_rate=None,
                fx_fee=None,
            )
            transactions.insert(0, opening_tx)

        return transactions


# Auto-register parser instance
_parser = AIBDebitParser()
from .registry import register_parser

register_parser(_parser)
