"""Tests for Revolut debit account statement parser."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from parsers.revolut_debit import RevolutDebitParser


class TestRevolutDebitParserCanParse:
    """Tests for can_parse() method."""

    def test_recognizes_valid_revolut_bank_uab_statement(self):
        """Parser recognizes valid Revolut Bank UAB statement."""
        # Arrange
        pdf_text = """
        EUR Statement
        Generated on the 19 Jan 2026
        Revolut Bank UAB
        Account transactions from 1 July 2025 to 19 January 2026
        """
        parser = RevolutDebitParser()
        
        # Act
        result = parser.can_parse(pdf_text)
        
        # Assert
        assert result is True

    def test_recognizes_valid_revolut_ltd_statement(self):
        """Parser recognizes valid Revolut Ltd statement."""
        # Arrange
        pdf_text = """
        EUR Statement
        Generated on the 19 Jan 2026
        Revolut Ltd
        Account transactions from 20 December 2019 to 3 December 2020
        """
        parser = RevolutDebitParser()
        
        # Act
        result = parser.can_parse(pdf_text)
        
        # Assert
        assert result is True

    def test_rejects_text_without_eur_statement(self):
        """Parser rejects text missing 'EUR Statement'."""
        # Arrange
        pdf_text = "Revolut Bank UAB Account transactions from 1 July 2025 to 19 January 2026"
        parser = RevolutDebitParser()
        
        # Act
        result = parser.can_parse(pdf_text)
        
        # Assert
        assert result is False

    def test_rejects_text_without_revolut_identifier(self):
        """Parser rejects text missing 'Revolut Bank UAB' or 'Revolut Ltd'."""
        # Arrange
        pdf_text = "EUR Statement Account transactions from 1 July 2025 to 19 January 2026"
        parser = RevolutDebitParser()
        
        # Act
        result = parser.can_parse(pdf_text)
        
        # Assert
        assert result is False

    def test_rejects_text_without_account_transactions(self):
        """Parser rejects text missing 'Account transactions from'."""
        # Arrange
        pdf_text = "EUR Statement Revolut Bank UAB"
        parser = RevolutDebitParser()
        
        # Act
        result = parser.can_parse(pdf_text)
        
        # Assert
        assert result is False


class TestRevolutDebitParserExtractDates:
    """Tests for extract_dates() method."""

    @patch('parsers.revolut_debit.PdfReader')
    def test_extracts_first_and_last_transaction_dates(self, mock_reader_class):
        """Dates are extracted from first and last transaction dates across all sections."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page = Mock()
        mock_page.extract_text.return_value = """
        EUR Statement
        Generated on the 20 Jan 2026
        Revolut Bank UAB
        Account transactions from 1 July 2025 to 19 January 2026
        Date Description Money out Money in Balance
        5 Jul 2025 - 5 Jul 2025 Top-up €50.00 €50.00
        10 Jul 2025 - 10 Jul 2025 Transfer €20.00 €30.00
        15 Jan 2026 - 15 Jan 2026 Payment €10.00 €20.00
        """
        
        mock_reader.pages = [mock_page]
        
        # Act
        parser = RevolutDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is not None
        assert result[0] == "5 Jul 2025"  # First transaction
        assert result[1] == "15 Jan 2026"  # Last transaction

    @patch('parsers.revolut_debit.PdfReader')
    def test_extracts_dates_across_multiple_sections(self, mock_reader_class):
        """Dates are extracted from transactions across Account, Pockets, and other sections."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = """
        Account transactions from 1 January 2024 to 31 March 2024
        5 Jan 2024 - 5 Jan 2024 Top-up €100.00
        10 Feb 2024 - 10 Feb 2024 Transfer €50.00
        """
        
        mock_page2 = Mock()
        mock_page2.extract_text.return_value = """
        Pockets transactions from 1 January 2024 to 31 March 2024
        15 Jan 2024 - 15 Jan 2024 To pocket €20.00
        20 Mar 2024 - 20 Mar 2024 From pocket €10.00
        """
        
        mock_reader.pages = [mock_page1, mock_page2]
        
        # Act
        parser = RevolutDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is not None
        assert result[0] == "5 Jan 2024"  # First transaction across all sections
        assert result[1] == "20 Mar 2024"  # Last transaction across all sections

    @patch('parsers.revolut_debit.PdfReader')
    def test_handles_single_digit_days(self, mock_reader_class):
        """Single-digit days are correctly parsed from transactions."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Account transactions from 1 March 2023 to 30 April 2023
        5 Mar 2023 - 5 Mar 2023 Transaction €10.00
        9 Apr 2023 - 9 Apr 2023 Transaction €20.00
        """
        
        mock_reader.pages = [mock_page]
        
        # Act
        parser = RevolutDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is not None
        assert result[0] == "5 Mar 2023"
        assert result[1] == "9 Apr 2023"

    @patch('parsers.revolut_debit.PdfReader')
    def test_searches_all_pages_for_transactions(self, mock_reader_class):
        """Transactions are searched across all pages to find first and last."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = """
        EUR Statement Page 1
        20 Dec 2019 - 20 Dec 2019 First transaction €10.00
        """
        
        mock_page2 = Mock()
        mock_page2.extract_text.return_value = """
        Account transactions from 20 December 2019 to 3 December 2020
        3 Dec 2020 - 3 Dec 2020 Last transaction €20.00
        """
        
        mock_reader.pages = [mock_page1, mock_page2]
        
        # Act
        parser = RevolutDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is not None
        assert result[0] == "20 Dec 2019"
        assert result[1] == "3 Dec 2020"

    @patch('parsers.revolut_debit.PdfReader')
    def test_returns_none_when_no_transactions_found(self, mock_reader_class):
        """Returns None when no transaction dates are found."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page = Mock()
        mock_page.extract_text.return_value = """
        EUR Statement
        Revolut Bank UAB
        Account transactions from 1 January 2024 to 31 January 2024
        Some other content without transaction dates
        """
        
        mock_reader.pages = [mock_page]
        
        # Act
        parser = RevolutDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is None

    @patch('parsers.revolut_debit.PdfReader')
    def test_handles_exception_gracefully(self, mock_reader_class):
        """Exception during PDF reading returns None."""
        # Arrange
        mock_reader_class.side_effect = Exception("PDF reading error")
        
        # Act
        parser = RevolutDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is None

    @patch('parsers.revolut_debit.PdfReader')
    def test_skips_empty_pages(self, mock_reader_class):
        """Empty pages are skipped when searching for date range."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_empty = Mock()
        mock_empty.extract_text.return_value = ""
        
        mock_content = Mock()
        mock_content.extract_text.return_value = """
        Account transactions from 10 October 2022 to 11 November 2022
        10 Oct 2022 - 10 Oct 2022 First transaction €10.00
        11 Nov 2022 - 11 Nov 2022 Last transaction €20.00
        """
        
        mock_reader.pages = [mock_empty, mock_content, mock_empty]
        
        # Act
        parser = RevolutDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is not None
        assert result[0] == "10 Oct 2022"
        assert result[1] == "11 Nov 2022"

    @patch('parsers.revolut_debit.PdfReader')
    def test_handles_case_insensitive_month_abbreviations(self, mock_reader_class):
        """Month abbreviations are matched case-insensitively in transactions."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Account transactions from 1 July 2025 to 19 January 2026
        1 JUL 2025 - 1 JUL 2025 Transaction €10.00
        19 jan 2026 - 19 jan 2026 Transaction €20.00
        """
        
        mock_reader.pages = [mock_page]
        
        # Act
        parser = RevolutDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is not None
        assert result[0] == "1 Jul 2025"
        assert result[1] == "19 Jan 2026"
