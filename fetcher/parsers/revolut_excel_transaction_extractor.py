"""Transaction extractor for Revolut Excel account statements.

Revolut provides account data in Excel (.xlsx) format with structured columns:
- Type, Product, Started Date, Completed Date, Description
- Amount, Fee, Currency, State, Balance

This extractor converts Revolut Excel data to the standard Transaction model.
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd

from models import Transaction

logger = logging.getLogger(__name__)

# Column names in Revolut Excel exports
COLUMN_TYPE = "Type"
COLUMN_PRODUCT = "Product"
COLUMN_STARTED_DATE = "Started Date"
COLUMN_COMPLETED_DATE = "Completed Date"
COLUMN_DESCRIPTION = "Description"
COLUMN_AMOUNT = "Amount"
COLUMN_FEE = "Fee"
COLUMN_CURRENCY = "Currency"
COLUMN_STATE = "State"
COLUMN_BALANCE = "Balance"

# Valid states (filter out REVERTED)
STATE_COMPLETED = "COMPLETED"

# Default product to extract
DEFAULT_PRODUCT = "Current"


class RevolutExcelTransactionExtractor:
    """Extractor for Revolut Excel account statements."""

    name = "Revolut Excel"

    def __init__(self, product: str = DEFAULT_PRODUCT):
        """
        Initialize the extractor.

        Args:
            product: Product type to extract (Current, Savings, Deposit).
                     Default is "Current".
        """
        self.product = product

    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this extractor can handle the given file.

        Args:
            file_path: Path to the file

        Returns:
            True if this is a Revolut Excel file
        """
        if not file_path.suffix.lower() == ".xlsx":
            return False

        try:
            # Read just the header to check columns
            df = pd.read_excel(file_path, nrows=0)
            required_columns = {
                COLUMN_TYPE,
                COLUMN_PRODUCT,
                COLUMN_COMPLETED_DATE,
                COLUMN_DESCRIPTION,
                COLUMN_AMOUNT,
                COLUMN_STATE,
            }
            return required_columns.issubset(set(df.columns))
        except Exception:
            return False

    def extract_dates(self, file_path: Path) -> tuple[str, str] | None:
        """
        Extract start and end dates from a Revolut Excel statement.

        Args:
            file_path: Path to the Excel file

        Returns:
            Tuple of (start_date, end_date) as strings in 'DD MMM YYYY' format,
            or None if dates cannot be extracted.
        """
        try:
            df = pd.read_excel(file_path)

            # Filter by product and completed state
            filtered = df[
                (df[COLUMN_PRODUCT] == self.product)
                & (df[COLUMN_STATE] == STATE_COMPLETED)
            ]

            if filtered.empty:
                return None

            # Get min and max completed dates
            completed_dates = filtered[COLUMN_COMPLETED_DATE].dropna()
            if completed_dates.empty:
                return None

            min_date = completed_dates.min()
            max_date = completed_dates.max()

            # Format as 'DD MMM YYYY'
            start_str = self._format_date(min_date)
            end_str = self._format_date(max_date)

            return (start_str, end_str)

        except Exception as e:
            logger.error("Failed to extract dates from %s: %s", file_path, e)
            return None

    def extract_transactions(self, file_path: Path) -> list[Transaction]:
        """
        Extract transaction records from a Revolut Excel statement.

        Args:
            file_path: Path to the Excel file

        Returns:
            List of Transaction objects, or empty list if extraction fails
        """
        try:
            df = pd.read_excel(file_path)

            # Filter by product and completed state
            filtered = df[
                (df[COLUMN_PRODUCT] == self.product)
                & (df[COLUMN_STATE] == STATE_COMPLETED)
            ].copy()

            if filtered.empty:
                logger.warning(
                    "No completed transactions found for product '%s' in %s",
                    self.product,
                    file_path.name,
                )
                return []

            # Sort by completed date
            filtered = filtered.sort_values(COLUMN_COMPLETED_DATE)

            transactions = []
            for _, row in filtered.iterrows():
                tx = self._row_to_transaction(row)
                if tx:
                    transactions.append(tx)

            logger.info(
                "Extracted %d transactions for product '%s' from %s",
                len(transactions),
                self.product,
                file_path.name,
            )
            return transactions

        except Exception as e:
            logger.error(
                "Failed to extract transactions from %s: %s",
                file_path,
                e,
                exc_info=True,
            )
            return []

    def _row_to_transaction(self, row: pd.Series) -> Optional[Transaction]:
        """
        Convert a DataFrame row to a Transaction object.

        Args:
            row: pandas Series representing a single transaction row

        Returns:
            Transaction object or None if conversion fails
        """
        try:
            amount = float(row[COLUMN_AMOUNT])
            fee = float(row[COLUMN_FEE]) if pd.notna(row[COLUMN_FEE]) else 0.0

            # Determine transaction type from amount sign
            # Positive = Credit (money in), Negative = Debit (money out)
            if amount >= 0:
                transaction_type = "Credit"
                abs_amount = amount
            else:
                transaction_type = "Debit"
                abs_amount = abs(amount)

            # Format date as 'DD MMM YYYY'
            completed_date = row[COLUMN_COMPLETED_DATE]
            if pd.isna(completed_date):
                # Fallback to started date if completed is null
                completed_date = row[COLUMN_STARTED_DATE]

            date_str = self._format_date(completed_date)

            # Get balance (may be null)
            balance = (
                float(row[COLUMN_BALANCE]) if pd.notna(row[COLUMN_BALANCE]) else None
            )

            # Build description from type and description
            tx_type = str(row[COLUMN_TYPE]) if pd.notna(row[COLUMN_TYPE]) else ""
            description = (
                str(row[COLUMN_DESCRIPTION])
                if pd.notna(row[COLUMN_DESCRIPTION])
                else ""
            )
            details = f"[{tx_type}] {description}".strip()

            return Transaction(
                amount=abs_amount,
                currency=(
                    str(row[COLUMN_CURRENCY])
                    if pd.notna(row[COLUMN_CURRENCY])
                    else "EUR"
                ),
                transaction_type=transaction_type,
                details=details,
                transaction_date=date_str,
                balance=balance,
                fee=fee if fee != 0.0 else None,
            )

        except Exception as e:
            logger.warning("Failed to convert row to transaction: %s", e)
            return None

    def _format_date(self, dt: datetime) -> str:
        """
        Format a datetime as 'DD MMM YYYY' string.

        Args:
            dt: datetime object

        Returns:
            Formatted date string
        """
        if isinstance(dt, str):
            # Already a string, try to parse and reformat
            try:
                dt = datetime.fromisoformat(dt)
            except ValueError:
                return dt

        # Use platform-independent formatting
        day = dt.day
        month = dt.strftime("%b")
        year = dt.year
        return f"{day} {month} {year}"

    def get_available_products(self, file_path: Path) -> list[str]:
        """
        Get list of available products in the Excel file.

        Args:
            file_path: Path to the Excel file

        Returns:
            List of unique product names
        """
        try:
            df = pd.read_excel(file_path)
            return df[COLUMN_PRODUCT].dropna().unique().tolist()
        except Exception:
            return []
