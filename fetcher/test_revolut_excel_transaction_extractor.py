"""Tests for Revolut Excel transaction extractor."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime

import pandas as pd

from parsers.revolut_excel_transaction_extractor import (
    RevolutExcelTransactionExtractor,
    COLUMN_TYPE,
    COLUMN_PRODUCT,
    COLUMN_STARTED_DATE,
    COLUMN_COMPLETED_DATE,
    COLUMN_DESCRIPTION,
    COLUMN_AMOUNT,
    COLUMN_FEE,
    COLUMN_CURRENCY,
    COLUMN_STATE,
    COLUMN_BALANCE,
)


def create_mock_dataframe(rows: list[dict]) -> pd.DataFrame:
    """Create a mock DataFrame from row dictionaries."""
    return pd.DataFrame(rows)


class TestRevolutExcelCanParse:
    """Tests for can_parse() method."""

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_recognizes_valid_revolut_excel(self, mock_read_excel):
        """Parser recognizes valid Revolut Excel file with required columns."""
        # Arrange
        mock_df = pd.DataFrame(
            columns=[
                COLUMN_TYPE,
                COLUMN_PRODUCT,
                COLUMN_STARTED_DATE,
                COLUMN_COMPLETED_DATE,
                COLUMN_DESCRIPTION,
                COLUMN_AMOUNT,
                COLUMN_FEE,
                COLUMN_CURRENCY,
                COLUMN_STATE,
                COLUMN_BALANCE,
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor()

        # Act
        result = extractor.can_parse(Path("statement.xlsx"))

        # Assert
        assert result is True

    def test_rejects_non_xlsx_file(self):
        """Parser rejects non-xlsx files."""
        # Arrange
        extractor = RevolutExcelTransactionExtractor()

        # Act & Assert
        assert extractor.can_parse(Path("statement.pdf")) is False
        assert extractor.can_parse(Path("statement.csv")) is False
        assert extractor.can_parse(Path("statement.xls")) is False

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_rejects_excel_missing_required_columns(self, mock_read_excel):
        """Parser rejects Excel file missing required columns."""
        # Arrange
        mock_df = pd.DataFrame(columns=["Type", "Amount"])  # Missing other columns
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor()

        # Act
        result = extractor.can_parse(Path("statement.xlsx"))

        # Assert
        assert result is False

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_handles_read_exception_gracefully(self, mock_read_excel):
        """Parser handles file read errors gracefully."""
        # Arrange
        mock_read_excel.side_effect = Exception("File read error")
        extractor = RevolutExcelTransactionExtractor()

        # Act
        result = extractor.can_parse(Path("statement.xlsx"))

        # Assert
        assert result is False


class TestRevolutExcelExtractDates:
    """Tests for extract_dates() method."""

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_extracts_date_range_from_completed_transactions(self, mock_read_excel):
        """Extracts min and max dates from completed transactions."""
        # Arrange
        mock_df = create_mock_dataframe(
            [
                {
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_COMPLETED_DATE: datetime(2024, 1, 15, 10, 30, 0),
                },
                {
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_COMPLETED_DATE: datetime(2024, 6, 20, 14, 0, 0),
                },
                {
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_COMPLETED_DATE: datetime(2024, 3, 5, 9, 0, 0),
                },
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor(product="Current")

        # Act
        result = extractor.extract_dates(Path("statement.xlsx"))

        # Assert
        assert result is not None
        assert result[0] == "15 Jan 2024"
        assert result[1] == "20 Jun 2024"

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_filters_by_product(self, mock_read_excel):
        """Only includes transactions for specified product."""
        # Arrange
        mock_df = create_mock_dataframe(
            [
                {
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_COMPLETED_DATE: datetime(2024, 1, 1),
                },
                {
                    COLUMN_PRODUCT: "Savings",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_COMPLETED_DATE: datetime(2024, 12, 31),
                },
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor(product="Current")

        # Act
        result = extractor.extract_dates(Path("statement.xlsx"))

        # Assert
        assert result is not None
        assert result[0] == "1 Jan 2024"
        assert result[1] == "1 Jan 2024"  # Only Current product transaction

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_excludes_reverted_transactions(self, mock_read_excel):
        """Excludes transactions with REVERTED state from date range."""
        # Arrange
        mock_df = create_mock_dataframe(
            [
                {
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_COMPLETED_DATE: datetime(2024, 3, 15),
                },
                {
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STATE: "REVERTED",
                    COLUMN_COMPLETED_DATE: None,
                },
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor(product="Current")

        # Act
        result = extractor.extract_dates(Path("statement.xlsx"))

        # Assert
        assert result is not None
        assert result[0] == "15 Mar 2024"
        assert result[1] == "15 Mar 2024"

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_returns_none_when_no_transactions_found(self, mock_read_excel):
        """Returns None when no matching transactions exist."""
        # Arrange
        mock_df = create_mock_dataframe(
            [
                {
                    COLUMN_PRODUCT: "Savings",  # Different product
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_COMPLETED_DATE: datetime(2024, 1, 1),
                },
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor(product="Current")

        # Act
        result = extractor.extract_dates(Path("statement.xlsx"))

        # Assert
        assert result is None


class TestRevolutExcelExtractTransactions:
    """Tests for extract_transactions() method."""

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_extracts_credit_transaction(self, mock_read_excel):
        """Extracts credit transaction (positive amount) correctly."""
        # Arrange
        mock_df = create_mock_dataframe(
            [
                {
                    COLUMN_TYPE: "Topup",
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STARTED_DATE: datetime(2024, 5, 10, 12, 0, 0),
                    COLUMN_COMPLETED_DATE: datetime(2024, 5, 10, 12, 0, 5),
                    COLUMN_DESCRIPTION: "Top-up by *1234",
                    COLUMN_AMOUNT: 100.00,
                    COLUMN_FEE: 0.0,
                    COLUMN_CURRENCY: "EUR",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_BALANCE: 100.00,
                },
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor(product="Current")

        # Act
        result = extractor.extract_transactions(Path("statement.xlsx"))

        # Assert
        assert len(result) == 1
        tx = result[0]
        assert tx.amount == 100.00
        assert tx.transaction_type == "Credit"
        assert tx.transaction_date == "10 May 2024"
        assert tx.details == "[Topup] Top-up by *1234"
        assert tx.balance == 100.00
        assert tx.currency == "EUR"
        assert tx.fee is None  # 0.0 fee is converted to None

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_extracts_debit_transaction(self, mock_read_excel):
        """Extracts debit transaction (negative amount) correctly."""
        # Arrange
        mock_df = create_mock_dataframe(
            [
                {
                    COLUMN_TYPE: "Transfer",
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STARTED_DATE: datetime(2024, 6, 15, 10, 0, 0),
                    COLUMN_COMPLETED_DATE: datetime(2024, 6, 15, 10, 0, 0),
                    COLUMN_DESCRIPTION: "Transfer to TEST RECIPIENT",
                    COLUMN_AMOUNT: -50.00,
                    COLUMN_FEE: 0.0,
                    COLUMN_CURRENCY: "EUR",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_BALANCE: 50.00,
                },
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor(product="Current")

        # Act
        result = extractor.extract_transactions(Path("statement.xlsx"))

        # Assert
        assert len(result) == 1
        tx = result[0]
        assert tx.amount == 50.00  # Absolute value
        assert tx.transaction_type == "Debit"
        assert tx.details == "[Transfer] Transfer to TEST RECIPIENT"

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_extracts_transaction_with_fee(self, mock_read_excel):
        """Extracts transaction with non-zero fee."""
        # Arrange
        mock_df = create_mock_dataframe(
            [
                {
                    COLUMN_TYPE: "Exchange",
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STARTED_DATE: datetime(2024, 7, 1, 15, 0, 0),
                    COLUMN_COMPLETED_DATE: datetime(2024, 7, 1, 15, 0, 0),
                    COLUMN_DESCRIPTION: "Exchanged to EUR",
                    COLUMN_AMOUNT: 141.56,
                    COLUMN_FEE: 1.42,
                    COLUMN_CURRENCY: "EUR",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_BALANCE: 154.99,
                },
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor(product="Current")

        # Act
        result = extractor.extract_transactions(Path("statement.xlsx"))

        # Assert
        assert len(result) == 1
        tx = result[0]
        assert tx.amount == 141.56
        assert tx.fee == 1.42
        assert tx.balance == 154.99

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_extracts_charge_with_zero_amount_and_fee(self, mock_read_excel):
        """Extracts charge transaction where amount=0 but fee>0."""
        # Arrange
        mock_df = create_mock_dataframe(
            [
                {
                    COLUMN_TYPE: "Charge",
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STARTED_DATE: datetime(2024, 8, 19, 2, 10, 0),
                    COLUMN_COMPLETED_DATE: datetime(2024, 8, 19, 2, 10, 24),
                    COLUMN_DESCRIPTION: "Premium plan fee",
                    COLUMN_AMOUNT: 0.00,
                    COLUMN_FEE: 1.23,
                    COLUMN_CURRENCY: "EUR",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_BALANCE: 2566.92,
                },
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor(product="Current")

        # Act
        result = extractor.extract_transactions(Path("statement.xlsx"))

        # Assert
        assert len(result) == 1
        tx = result[0]
        assert tx.amount == 0.00
        assert tx.transaction_type == "Credit"  # 0 is non-negative
        assert tx.fee == 1.23
        assert tx.details == "[Charge] Premium plan fee"

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_filters_by_product(self, mock_read_excel):
        """Only extracts transactions for specified product."""
        # Arrange
        mock_df = create_mock_dataframe(
            [
                {
                    COLUMN_TYPE: "Topup",
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STARTED_DATE: datetime(2024, 1, 1),
                    COLUMN_COMPLETED_DATE: datetime(2024, 1, 1),
                    COLUMN_DESCRIPTION: "Current topup",
                    COLUMN_AMOUNT: 100.00,
                    COLUMN_FEE: 0.0,
                    COLUMN_CURRENCY: "EUR",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_BALANCE: 100.00,
                },
                {
                    COLUMN_TYPE: "Transfer",
                    COLUMN_PRODUCT: "Savings",
                    COLUMN_STARTED_DATE: datetime(2024, 1, 2),
                    COLUMN_COMPLETED_DATE: datetime(2024, 1, 2),
                    COLUMN_DESCRIPTION: "Savings transfer",
                    COLUMN_AMOUNT: 50.00,
                    COLUMN_FEE: 0.0,
                    COLUMN_CURRENCY: "EUR",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_BALANCE: 50.00,
                },
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor(product="Current")

        # Act
        result = extractor.extract_transactions(Path("statement.xlsx"))

        # Assert
        assert len(result) == 1
        assert "Current topup" in result[0].details

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_excludes_reverted_transactions(self, mock_read_excel):
        """Excludes transactions with REVERTED state."""
        # Arrange
        mock_df = create_mock_dataframe(
            [
                {
                    COLUMN_TYPE: "Topup",
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STARTED_DATE: datetime(2024, 1, 1),
                    COLUMN_COMPLETED_DATE: datetime(2024, 1, 1),
                    COLUMN_DESCRIPTION: "Completed topup",
                    COLUMN_AMOUNT: 100.00,
                    COLUMN_FEE: 0.0,
                    COLUMN_CURRENCY: "EUR",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_BALANCE: 100.00,
                },
                {
                    COLUMN_TYPE: "Topup",
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STARTED_DATE: datetime(2024, 1, 2),
                    COLUMN_COMPLETED_DATE: None,
                    COLUMN_DESCRIPTION: "Failed topup",
                    COLUMN_AMOUNT: 500.00,
                    COLUMN_FEE: 0.0,
                    COLUMN_CURRENCY: "EUR",
                    COLUMN_STATE: "REVERTED",
                    COLUMN_BALANCE: None,
                },
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor(product="Current")

        # Act
        result = extractor.extract_transactions(Path("statement.xlsx"))

        # Assert
        assert len(result) == 1
        assert "Completed topup" in result[0].details

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_sorts_by_completed_date(self, mock_read_excel):
        """Transactions are sorted by completed date."""
        # Arrange
        mock_df = create_mock_dataframe(
            [
                {
                    COLUMN_TYPE: "Transfer",
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STARTED_DATE: datetime(2024, 3, 1),
                    COLUMN_COMPLETED_DATE: datetime(2024, 3, 15),
                    COLUMN_DESCRIPTION: "Third",
                    COLUMN_AMOUNT: -30.00,
                    COLUMN_FEE: 0.0,
                    COLUMN_CURRENCY: "EUR",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_BALANCE: 70.00,
                },
                {
                    COLUMN_TYPE: "Topup",
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STARTED_DATE: datetime(2024, 1, 1),
                    COLUMN_COMPLETED_DATE: datetime(2024, 1, 1),
                    COLUMN_DESCRIPTION: "First",
                    COLUMN_AMOUNT: 100.00,
                    COLUMN_FEE: 0.0,
                    COLUMN_CURRENCY: "EUR",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_BALANCE: 100.00,
                },
                {
                    COLUMN_TYPE: "Transfer",
                    COLUMN_PRODUCT: "Current",
                    COLUMN_STARTED_DATE: datetime(2024, 2, 1),
                    COLUMN_COMPLETED_DATE: datetime(2024, 2, 10),
                    COLUMN_DESCRIPTION: "Second",
                    COLUMN_AMOUNT: -20.00,
                    COLUMN_FEE: 0.0,
                    COLUMN_CURRENCY: "EUR",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_BALANCE: 80.00,
                },
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor(product="Current")

        # Act
        result = extractor.extract_transactions(Path("statement.xlsx"))

        # Assert
        assert len(result) == 3
        assert "First" in result[0].details
        assert "Second" in result[1].details
        assert "Third" in result[2].details

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_handles_exception_gracefully(self, mock_read_excel):
        """Returns empty list on exception."""
        # Arrange
        mock_read_excel.side_effect = Exception("File error")
        extractor = RevolutExcelTransactionExtractor(product="Current")

        # Act
        result = extractor.extract_transactions(Path("statement.xlsx"))

        # Assert
        assert result == []

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_returns_empty_list_when_no_matching_transactions(self, mock_read_excel):
        """Returns empty list when no transactions match filters."""
        # Arrange
        mock_df = create_mock_dataframe(
            [
                {
                    COLUMN_TYPE: "Transfer",
                    COLUMN_PRODUCT: "Deposit",  # Different product
                    COLUMN_STARTED_DATE: datetime(2024, 1, 1),
                    COLUMN_COMPLETED_DATE: datetime(2024, 1, 1),
                    COLUMN_DESCRIPTION: "Deposit transfer",
                    COLUMN_AMOUNT: 1000.00,
                    COLUMN_FEE: 0.0,
                    COLUMN_CURRENCY: "EUR",
                    COLUMN_STATE: "COMPLETED",
                    COLUMN_BALANCE: 1000.00,
                },
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor(product="Current")

        # Act
        result = extractor.extract_transactions(Path("statement.xlsx"))

        # Assert
        assert result == []


class TestRevolutExcelGetAvailableProducts:
    """Tests for get_available_products() method."""

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_returns_unique_product_names(self, mock_read_excel):
        """Returns list of unique product names in file."""
        # Arrange
        mock_df = create_mock_dataframe(
            [
                {COLUMN_PRODUCT: "Current"},
                {COLUMN_PRODUCT: "Current"},
                {COLUMN_PRODUCT: "Savings"},
                {COLUMN_PRODUCT: "Deposit"},
            ]
        )
        mock_read_excel.return_value = mock_df
        extractor = RevolutExcelTransactionExtractor()

        # Act
        result = extractor.get_available_products(Path("statement.xlsx"))

        # Assert
        assert set(result) == {"Current", "Savings", "Deposit"}

    @patch("parsers.revolut_excel_transaction_extractor.pd.read_excel")
    def test_returns_empty_list_on_error(self, mock_read_excel):
        """Returns empty list when file cannot be read."""
        # Arrange
        mock_read_excel.side_effect = Exception("File error")
        extractor = RevolutExcelTransactionExtractor()

        # Act
        result = extractor.get_available_products(Path("statement.xlsx"))

        # Assert
        assert result == []


class TestRevolutExcelProductConfiguration:
    """Tests for product configuration."""

    def test_default_product_is_current(self):
        """Default product is 'Current'."""
        # Act
        extractor = RevolutExcelTransactionExtractor()

        # Assert
        assert extractor.product == "Current"

    def test_custom_product_can_be_set(self):
        """Custom product can be specified."""
        # Act
        extractor = RevolutExcelTransactionExtractor(product="Savings")

        # Assert
        assert extractor.product == "Savings"
