"""Tests for AIB debit account statement parser."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from parsers.aib_debit import AIBDebitParser


class TestAIBDebitParserCanParse:
    """Tests for can_parse() method."""

    def test_recognizes_valid_debit_statement(self):
        """Parser recognizes valid AIB debit account statement."""
        # Arrange
        pdf_text = """
        Statement of Account with Allied Irish Banks, p.l.c.
        Personal Bank Account
        Date of Statement
        31 Dec 2024
        """
        parser = AIBDebitParser()
        
        # Act
        result = parser.can_parse(pdf_text)
        
        # Assert
        assert result is True

    def test_rejects_text_without_statement_of_account(self):
        """Parser rejects text missing 'Statement of Account'."""
        # Arrange
        pdf_text = "Personal Bank Account Date of Statement"
        parser = AIBDebitParser()
        
        # Act
        result = parser.can_parse(pdf_text)
        
        # Assert
        assert result is False

    def test_rejects_text_without_personal_bank_account(self):
        """Parser rejects text missing 'Personal Bank Account'."""
        # Arrange
        pdf_text = "Statement of Account Date of Statement"
        parser = AIBDebitParser()
        
        # Act
        result = parser.can_parse(pdf_text)
        
        # Assert
        assert result is False

    def test_rejects_text_without_date_of_statement(self):
        """Parser rejects text missing 'Date of Statement'."""
        # Arrange
        pdf_text = "Statement of Account Personal Bank Account"
        parser = AIBDebitParser()
        
        # Act
        result = parser.can_parse(pdf_text)
        
        # Assert
        assert result is False


class TestAIBDebitParserExtractDates:
    """Tests for extract_dates() method."""

    @patch('parsers.aib_debit.PdfReader')
    def test_balance_forward_date_is_extracted_as_start_date(self, mock_reader_class):
        """Statement with BALANCE FORWARD extracts that date as start date."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = """
Date Details Debit € Credit € Balance €
3 Apr 2017 BALANCE FORWARD 1234.56
5 Apr 2017 Interest Rate
TEST TRANSACTION 100.00
        """
        
        mock_page_last = Mock()
        mock_page_last.extract_text.return_value = """
Date of Statement
28 Apr 2017
IBAN: IE12 BANK 1234 5612 3456 78
        """
        
        mock_reader.pages = [mock_page1, mock_page_last]
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is not None
        assert result[0] == "3 Apr 2017"
        assert result[1] == "28 Apr 2017"

    @patch('parsers.aib_debit.PdfReader')
    def test_first_transaction_date_used_when_no_balance_forward(self, mock_reader_class):
        """When no BALANCE FORWARD exists, first transaction date is used as start date."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = """
Date Details Debit € Credit € Balance €
8 May 2016 Interest Rate
TEST TRANSACTION 250.00
LOCATION
        """
        
        mock_page_last = Mock()
        mock_page_last.extract_text.return_value = """
Date of Statement
31 May 2016
IBAN: IE98 BANK 7654 3298 7654 32
        """
        
        mock_reader.pages = [mock_page1, mock_page_last]
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is not None
        assert result[0] == "8 May 2016"
        assert result[1] == "31 May 2016"

    @patch('parsers.aib_debit.PdfReader')
    def test_empty_pages_are_skipped_correctly(self, mock_reader_class):
        """Empty pages are skipped and dates extracted from pages with content."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_empty_page = Mock()
        mock_empty_page.extract_text.return_value = ""
        
        mock_content_page = Mock()
        mock_content_page.extract_text.return_value = """
Date of Statement
15 Nov 2016
4 Oct 2016 BALANCE FORWARD 2345.67
        """
        
        mock_reader.pages = [mock_content_page, mock_empty_page, mock_empty_page]
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is not None
        assert result[0] == "4 Oct 2016"
        assert result[1] == "15 Nov 2016"

    @patch('parsers.aib_debit.PdfReader')
    def test_none_returned_when_no_statement_date_found(self, mock_reader_class):
        """None is returned when Date of Statement pattern is not found in PDF."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page = Mock()
        mock_page.extract_text.return_value = "Some random content without dates"
        
        mock_reader.pages = [mock_page]
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is None

    @patch('parsers.aib_debit.PdfReader')
    def test_exception_in_pdf_reading_returns_none(self, mock_reader_class):
        """Exception during PDF reading is handled gracefully and returns None."""
        # Arrange
        mock_reader_class.side_effect = Exception("PDF reading error")
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is None

    @patch('parsers.aib_debit.PdfReader')
    def test_date_of_statement_in_context_is_skipped_for_start_date(self, mock_reader_class):
        """Transaction date outside Date of Statement context is extracted correctly."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page = Mock()
        mock_page.extract_text.return_value = """
Page Number 1
Date of Statement
20 Jul 2015
IBAN: IE11 BANK 2233 4411 2233 44

Date Details Debit € Credit € Balance €
5 Jul 2015 TEST MERCHANT 150.00 3500.00
6 Jul 2015 ANOTHER TRANSACTION 25.00 3475.00
        """
        
        mock_reader.pages = [mock_page]
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is not None
        assert result[0] == "5 Jul 2015"
        assert result[1] == "20 Jul 2015"

    @patch('parsers.aib_debit.PdfReader')
    def test_pdf_with_only_empty_pages_returns_none(self, mock_reader_class):
        """PDF containing only empty or very short pages returns None."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_empty = Mock()
        mock_empty.extract_text.return_value = ""
        
        mock_reader.pages = [mock_empty, mock_empty, mock_empty]
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_dates(Path("empty.pdf"))
        
        # Assert
        assert result is None

    @patch('parsers.aib_debit.PdfReader')
    def test_pdf_with_malformed_date_format_falls_back_gracefully(self, mock_reader_class):
        """PDF with dates in unexpected format uses end date as start date fallback."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_page = Mock()
        mock_page.extract_text.return_value = """
Date of Statement
18 Oct 2007
Some text 2007-10-05 in wrong format
        """
        
        mock_reader.pages = [mock_page]
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_dates(Path("malformed.pdf"))
        
        # Assert
        assert result is not None
        assert result[0] == "18 Oct 2007"
        assert result[1] == "18 Oct 2007"

    @patch('parsers.aib_debit.PdfReader')
    def test_short_pages_are_skipped_for_end_date(self, mock_reader_class):
        """Pages with less than 50 characters are skipped when searching for end date."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader
        
        mock_short_page = Mock()
        mock_short_page.extract_text.return_value = "Short"
        
        mock_content_page = Mock()
        mock_content_page.extract_text.return_value = """
Date of Statement
30 Jun 2018
IBAN: IE12 BANK 1234 5612 3456 78
Additional content to ensure page has more than 50 characters
        """
        
        mock_reader.pages = [mock_short_page, mock_content_page]
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))
        
        # Assert
        assert result is not None
        assert result[1] == "30 Jun 2018"
