"""Tests for AIB credit card statement parser."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from parsers.aib_credit import AIBCreditParser


class TestAIBCreditParserCanParse:
    """Tests for can_parse() method."""

    def test_recognizes_valid_credit_statement(self):
        """Parser recognizes valid AIB credit card statement."""
        # Arrange
        pdf_text = """
        Credit Limit: €5,000.00
        Account Statement - 11th January, 2026
        """
        parser = AIBCreditParser()

        # Act
        result = parser.can_parse(pdf_text)

        # Assert
        assert result is True

    def test_rejects_text_without_credit_limit(self):
        """Parser rejects text missing 'Credit Limit'."""
        # Arrange
        pdf_text = "Account Statement - 11th January, 2026"
        parser = AIBCreditParser()

        # Act
        result = parser.can_parse(pdf_text)

        # Assert
        assert result is False

    def test_rejects_text_without_account_statement(self):
        """Parser rejects text missing 'Account Statement'."""
        # Arrange
        pdf_text = "Credit Limit: €5,000.00"
        parser = AIBCreditParser()

        # Act
        result = parser.can_parse(pdf_text)

        # Assert
        assert result is False


class TestAIBCreditParserExtractDates:
    """Tests for extract_dates() method."""

    @patch("parsers.aib_credit.PdfReader")
    def test_extracts_end_date_from_account_statement_header(self, mock_reader_class):
        """End date is extracted from 'Account Statement - DDth Month, YYYY' pattern."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader

        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Account Statement - 11th January, 2026
        Credit Limit: €5,000.00
        """

        mock_reader.pages = [mock_page]

        # Act
        parser = AIBCreditParser()
        result = parser.extract_dates(Path("dummy.pdf"))

        # Assert
        assert result is not None
        assert result[1] == "11 Jan 2026"

    @patch("parsers.aib_credit.PdfReader")
    def test_extracts_end_date_from_last_page(self, mock_reader_class):
        """End date is searched from last page backwards."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader

        mock_page1 = Mock()
        mock_page1.extract_text.return_value = "First page content"

        mock_page_last = Mock()
        mock_page_last.extract_text.return_value = """
        Account Statement - 15th February, 2025
        """

        mock_reader.pages = [mock_page1, mock_page_last]

        # Act
        parser = AIBCreditParser()
        result = parser.extract_dates(Path("dummy.pdf"))

        # Assert
        assert result is not None
        assert result[1] == "15 Feb 2025"

    @patch("parsers.aib_credit.PdfReader")
    def test_handles_ordinal_suffixes_in_date(self, mock_reader_class):
        """Parser handles ordinal suffixes (st, nd, rd, th) in date."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader

        test_cases = [
            ("1st", "1"),
            ("2nd", "2"),
            ("3rd", "3"),
            ("11th", "11"),
            ("21st", "21"),
            ("22nd", "22"),
            ("23rd", "23"),
        ]

        for ordinal, expected_day in test_cases:
            mock_page = Mock()
            mock_page.extract_text.return_value = f"""
            Account Statement - {ordinal} March, 2024
            """
            mock_reader.pages = [mock_page]

            # Act
            parser = AIBCreditParser()
            result = parser.extract_dates(Path("dummy.pdf"))

            # Assert
            assert result is not None
            assert result[1] == f"{expected_day} Mar 2024"

    @patch("parsers.aib_credit.PdfReader")
    def test_extracts_start_date_from_first_transaction(self, mock_reader_class):
        """Start date is extracted from first transaction date."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader

        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Account Statement - 11th January, 2026
        13 Dec 15 Dec MERCHANT NAME 50.00
        14 Dec 16 Dec ANOTHER MERCHANT 25.00
        """

        mock_reader.pages = [mock_page]

        # Act
        parser = AIBCreditParser()
        result = parser.extract_dates(Path("dummy.pdf"))

        # Assert
        assert result is not None
        assert result[0] == "13 Dec 2025"
        assert result[1] == "11 Jan 2026"

    @patch("parsers.aib_credit.PdfReader")
    def test_determines_year_for_transaction_before_statement_month(
        self, mock_reader_class
    ):
        """Transaction month before statement month uses same year."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader

        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Account Statement - 15th March, 2025
        5 Feb 6 Feb MERCHANT 100.00
        """

        mock_reader.pages = [mock_page]

        # Act
        parser = AIBCreditParser()
        result = parser.extract_dates(Path("dummy.pdf"))

        # Assert
        assert result is not None
        assert result[0] == "5 Feb 2025"

    @patch("parsers.aib_credit.PdfReader")
    def test_determines_year_for_transaction_after_statement_month(
        self, mock_reader_class
    ):
        """Transaction month after statement month uses previous year."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader

        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Account Statement - 15th January, 2025
        20 Dec 21 Dec MERCHANT 100.00
        """

        mock_reader.pages = [mock_page]

        # Act
        parser = AIBCreditParser()
        result = parser.extract_dates(Path("dummy.pdf"))

        # Assert
        assert result is not None
        assert result[0] == "20 Dec 2024"

    @patch("parsers.aib_credit.PdfReader")
    def test_uses_end_date_as_start_when_no_transactions_found(self, mock_reader_class):
        """When no transactions found, start date equals end date."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader

        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Account Statement - 31st December, 2024
        No transactions in this statement
        """

        mock_reader.pages = [mock_page]

        # Act
        parser = AIBCreditParser()
        result = parser.extract_dates(Path("dummy.pdf"))

        # Assert
        assert result is not None
        assert result[0] == "31 Dec 2024"
        assert result[1] == "31 Dec 2024"

    @patch("parsers.aib_credit.PdfReader")
    def test_returns_none_when_no_end_date_found(self, mock_reader_class):
        """Returns None when Account Statement pattern is not found."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader

        mock_page = Mock()
        mock_page.extract_text.return_value = "Random content without statement date"

        mock_reader.pages = [mock_page]

        # Act
        parser = AIBCreditParser()
        result = parser.extract_dates(Path("dummy.pdf"))

        # Assert
        assert result is None

    @patch("parsers.aib_credit.PdfReader")
    def test_handles_exception_gracefully(self, mock_reader_class):
        """Exception during PDF reading returns None."""
        # Arrange
        mock_reader_class.side_effect = Exception("PDF reading error")

        # Act
        parser = AIBCreditParser()
        result = parser.extract_dates(Path("dummy.pdf"))

        # Assert
        assert result is None

    @patch("parsers.aib_credit.PdfReader")
    def test_skips_empty_pages_when_searching(self, mock_reader_class):
        """Empty pages are skipped when searching for dates."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader

        mock_empty = Mock()
        mock_empty.extract_text.return_value = ""

        mock_content = Mock()
        mock_content.extract_text.return_value = """
        Account Statement - 20th June, 2023
        10 May 11 May MERCHANT 75.00
        """

        mock_reader.pages = [mock_empty, mock_content, mock_empty]

        # Act
        parser = AIBCreditParser()
        result = parser.extract_dates(Path("dummy.pdf"))

        # Assert
        assert result is not None
        assert result[0] == "10 May 2023"
        assert result[1] == "20 Jun 2023"


class TestAIBCreditParserExtractTransactions:
    """Tests for extract_transactions() method."""

    @patch("parsers.aib_credit.PdfReader")
    def test_extracts_simple_debit_transaction(self, mock_reader_class):
        """Extracts a simple debit transaction without CR suffix."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Account Statement - 15th January, 2025
        Transaction Date Posting Date Details
        5 Jan 5 Jan TEST MERCHANT 50.00
        """
        
        mock_reader.pages = [mock_page]
        
        # Act
        parser = AIBCreditParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert len(result) == 1
        assert result[0].amount == 50.00
        assert result[0].transaction_type == "Debit"
        assert result[0].transaction_date == "5 Jan 2025"
        assert result[0].posting_date == "5 Jan 2025"
        assert result[0].details == "TEST MERCHANT"

    @patch("parsers.aib_credit.PdfReader")
    def test_extracts_credit_transaction_with_cr_suffix(self, mock_reader_class):
        """Extracts a credit transaction identified by CR suffix."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Account Statement - 20th February, 2025
        Transaction Date Posting Date Details
        10 Feb 10 Feb DIRECT DEBIT - THANK YOU 2,522.86CR
        """
        
        mock_reader.pages = [mock_page]
        
        # Act
        parser = AIBCreditParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert len(result) == 1
        assert result[0].amount == 2522.86
        assert result[0].transaction_type == "Credit"
        assert result[0].transaction_date == "10 Feb 2025"
        assert result[0].details == "DIRECT DEBIT - THANK YOU"

    @patch("parsers.aib_credit.PdfReader")
    def test_extracts_transaction_with_reference(self, mock_reader_class):
        """Extracts transaction with reference number on following line."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Account Statement - 15th March, 2025
        Transaction Date Posting Date Details
        8 Mar 8 Mar MERCHANT NAME 75.50
        Ref: 123456789
        """
        
        mock_reader.pages = [mock_page]
        
        # Act
        parser = AIBCreditParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert len(result) == 1
        assert result[0].amount == 75.50
        assert result[0].reference == "123456789"

    @patch("parsers.aib_credit.PdfReader")
    def test_extracts_foreign_currency_transaction(self, mock_reader_class):
        """Extracts transaction with foreign currency information."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Account Statement - 25th April, 2025
        Transaction Date Posting Date Details
        15 Apr 15 Apr FOREIGN MERCHANT 100.00
        50.00 USD @ rate of 2.000000
        Currency Conversion Fee of 1.50
        """
        
        mock_reader.pages = [mock_page]
        
        # Act
        parser = AIBCreditParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert len(result) == 1
        assert result[0].amount == 100.00
        assert result[0].original_amount == 50.00
        assert result[0].original_currency == "USD"
        assert result[0].exchange_rate == 2.000000
        assert result[0].fx_fee == 1.50

    @patch("parsers.aib_credit.PdfReader")
    def test_extracts_multiple_transactions(self, mock_reader_class):
        """Extracts multiple transactions from the same statement."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Account Statement - 30th May, 2025
        Transaction Date Posting Date Details
        10 May 10 May MERCHANT ONE 25.00
        15 May 15 May MERCHANT TWO 50.00
        20 May 20 May MERCHANT THREE 100.00CR
        """
        
        mock_reader.pages = [mock_page]
        
        # Act
        parser = AIBCreditParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert len(result) == 3
        assert result[0].amount == 25.00
        assert result[0].transaction_type == "Debit"
        assert result[1].amount == 50.00
        assert result[1].transaction_type == "Debit"
        assert result[2].amount == 100.00
        assert result[2].transaction_type == "Credit"

    @patch("parsers.aib_credit.PdfReader")
    def test_handles_exception_gracefully(self, mock_reader_class):
        """Exception during PDF processing returns empty list."""
        # Arrange
        mock_reader_class.side_effect = Exception("PDF error")
        
        # Act
        parser = AIBCreditParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert result == []

    @patch("parsers.aib_credit.PdfReader")
    def test_returns_empty_list_when_no_transactions_found(self, mock_reader_class):
        """Returns empty list when no transaction section is found."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Account Statement - 15th June, 2025
        No transactions in this statement
        """
        
        mock_reader.pages = [mock_page]
        
        # Act
        parser = AIBCreditParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert result == []
