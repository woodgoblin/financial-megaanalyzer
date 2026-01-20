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

    @patch('parsers.aib_credit.PdfReader')
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

    @patch('parsers.aib_credit.PdfReader')
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

    @patch('parsers.aib_credit.PdfReader')
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

    @patch('parsers.aib_credit.PdfReader')
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

    @patch('parsers.aib_credit.PdfReader')
    def test_determines_year_for_transaction_before_statement_month(self, mock_reader_class):
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

    @patch('parsers.aib_credit.PdfReader')
    def test_determines_year_for_transaction_after_statement_month(self, mock_reader_class):
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

    @patch('parsers.aib_credit.PdfReader')
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

    @patch('parsers.aib_credit.PdfReader')
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

    @patch('parsers.aib_credit.PdfReader')
    def test_handles_exception_gracefully(self, mock_reader_class):
        """Exception during PDF reading returns None."""
        # Arrange
        mock_reader_class.side_effect = Exception("PDF reading error")
        
        # Act
        parser = AIBCreditParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is None

    @patch('parsers.aib_credit.PdfReader')
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
