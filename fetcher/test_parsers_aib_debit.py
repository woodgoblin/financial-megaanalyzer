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

    @patch("parsers.aib_debit.PdfReader")
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

    @patch("parsers.aib_debit.PdfReader")
    def test_first_transaction_date_used_when_no_balance_forward(
        self, mock_reader_class
    ):
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

    @patch("parsers.aib_debit.PdfReader")
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

    @patch("parsers.aib_debit.PdfReader")
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

    @patch("parsers.aib_debit.PdfReader")
    def test_exception_in_pdf_reading_returns_none(self, mock_reader_class):
        """Exception during PDF reading is handled gracefully and returns None."""
        # Arrange
        mock_reader_class.side_effect = Exception("PDF reading error")

        # Act
        parser = AIBDebitParser()
        result = parser.extract_dates(Path("dummy.pdf"))

        # Assert
        assert result is None

    @patch("parsers.aib_debit.PdfReader")
    def test_date_of_statement_in_context_is_skipped_for_start_date(
        self, mock_reader_class
    ):
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

    @patch("parsers.aib_debit.PdfReader")
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

    @patch("parsers.aib_debit.PdfReader")
    def test_pdf_with_malformed_date_format_falls_back_gracefully(
        self, mock_reader_class
    ):
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

    @patch("parsers.aib_debit.PdfReader")
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


class TestAIBDebitParserExtractTransactions:
    """Tests for extract_transactions() method."""

    @patch("parsers.aib_debit.pdfplumber")
    def test_extracts_simple_debit_transaction(self, mock_pdfplumber):
        """Extracts a simple debit transaction with amount in debit column."""
        # Arrange
        mock_pdf = Mock()
        mock_page = Mock()
        
        # Mock words with column positions
        # Header row: Debit at x=250, Credit at x=350, Balance at x=450
        # Transaction: date at x=50, description at x=100, amount at x=280 (debit column), balance at x=460
        mock_page.extract_words.return_value = [
            {'text': 'Date', 'x0': 50, 'x1': 90, 'top': 100},
            {'text': 'Details', 'x0': 100, 'x1': 200, 'top': 100},
            {'text': 'Debit', 'x0': 250, 'x1': 300, 'top': 100},
            {'text': 'Credit', 'x0': 350, 'x1': 400, 'top': 100},
            {'text': 'Balance', 'x0': 450, 'x1': 500, 'top': 100},
            {'text': '15', 'x0': 50, 'x1': 70, 'top': 150},
            {'text': 'Mar', 'x0': 75, 'x1': 100, 'top': 150},
            {'text': '2024', 'x0': 105, 'x1': 140, 'top': 150},
            {'text': 'TEST', 'x0': 150, 'x1': 190, 'top': 150},
            {'text': 'MERCHANT', 'x0': 195, 'x1': 270, 'top': 150},
            {'text': '100.00', 'x0': 280, 'x1': 330, 'top': 150},  # In debit column
            {'text': '5000.00', 'x0': 460, 'x1': 520, 'top': 150},  # Balance
        ]
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert len(result) == 1
        assert result[0].amount == 100.00
        assert result[0].transaction_type == "Debit"
        assert result[0].transaction_date == "15 Mar 2024"
        assert result[0].details == "TEST MERCHANT"
        assert result[0].balance == 5000.00

    @patch("parsers.aib_debit.pdfplumber")
    def test_extracts_simple_credit_transaction(self, mock_pdfplumber):
        """Extracts a simple credit transaction with amount in credit column."""
        # Arrange
        mock_pdf = Mock()
        mock_page = Mock()
        
        mock_page.extract_words.return_value = [
            {'text': 'Debit', 'x0': 250, 'x1': 300, 'top': 100},
            {'text': 'Credit', 'x0': 350, 'x1': 400, 'top': 100},
            {'text': 'Balance', 'x0': 450, 'x1': 500, 'top': 100},
            {'text': '20', 'x0': 50, 'x1': 70, 'top': 150},
            {'text': 'Apr', 'x0': 75, 'x1': 100, 'top': 150},
            {'text': '2024', 'x0': 105, 'x1': 140, 'top': 150},
            {'text': 'SALARY', 'x0': 150, 'x1': 200, 'top': 150},
            {'text': 'PAYMENT', 'x0': 195, 'x1': 240, 'top': 150},  # Before details_max_x (debit_range[0] = 200)
            {'text': '2500.00', 'x0': 360, 'x1': 410, 'top': 150},  # In credit column
            {'text': '7500.00', 'x0': 460, 'x1': 520, 'top': 150},  # Balance
        ]
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert len(result) == 1
        assert result[0].amount == 2500.00
        assert result[0].transaction_type == "Credit"
        assert result[0].transaction_date == "20 Apr 2024"
        assert result[0].details == "SALARY PAYMENT"
        assert result[0].balance == 7500.00

    @patch("parsers.aib_debit.pdfplumber")
    def test_extracts_opening_balance_transaction(self, mock_pdfplumber):
        """Extracts opening balance as a transaction with zero amount."""
        # Arrange
        mock_pdf = Mock()
        mock_page = Mock()
        
        mock_page.extract_words.return_value = [
            {'text': 'Debit', 'x0': 250, 'x1': 300, 'top': 100},
            {'text': 'Credit', 'x0': 350, 'x1': 400, 'top': 100},
            {'text': 'Balance', 'x0': 450, 'x1': 500, 'top': 100},
            {'text': '1', 'x0': 50, 'x1': 70, 'top': 150},
            {'text': 'Jan', 'x0': 75, 'x1': 100, 'top': 150},
            {'text': '2024', 'x0': 105, 'x1': 140, 'top': 150},
            {'text': 'OPENING', 'x0': 150, 'x1': 220, 'top': 150},
            {'text': 'BALANCE', 'x0': 225, 'x1': 290, 'top': 150},
            {'text': '1000.00', 'x0': 460, 'x1': 520, 'top': 150},  # Balance only
        ]
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert len(result) == 1
        assert result[0].amount == 0.0
        assert result[0].transaction_type == "Credit"
        assert result[0].details == "OPENING BALANCE"
        assert result[0].balance == 1000.00

    @patch("parsers.aib_debit.pdfplumber")
    def test_extracts_multiple_transactions_on_same_day(self, mock_pdfplumber):
        """Extracts multiple transactions that occur on the same day."""
        # Arrange
        mock_pdf = Mock()
        mock_page = Mock()
        
        mock_page.extract_words.return_value = [
            {'text': 'Debit', 'x0': 250, 'x1': 300, 'top': 100},
            {'text': 'Credit', 'x0': 350, 'x1': 400, 'top': 100},
            {'text': 'Balance', 'x0': 450, 'x1': 500, 'top': 100},
            # First transaction
            {'text': '10', 'x0': 50, 'x1': 70, 'top': 150},
            {'text': 'May', 'x0': 75, 'x1': 100, 'top': 150},
            {'text': '2024', 'x0': 105, 'x1': 140, 'top': 150},
            {'text': 'MERCHANT1', 'x0': 150, 'x1': 230, 'top': 150},
            {'text': '50.00', 'x0': 280, 'x1': 330, 'top': 150},  # Debit
            {'text': '4950.00', 'x0': 460, 'x1': 520, 'top': 150},
            # Second transaction (same day, no date repeated)
            {'text': 'MERCHANT2', 'x0': 150, 'x1': 230, 'top': 180},
            {'text': '25.00', 'x0': 280, 'x1': 330, 'top': 180},  # Debit
            {'text': '4925.00', 'x0': 460, 'x1': 520, 'top': 180},
        ]
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert len(result) == 2
        assert result[0].amount == 50.00
        assert result[0].transaction_date == "10 May 2024"
        assert result[0].details == "MERCHANT1"
        assert result[1].amount == 25.00
        assert result[1].transaction_date == "10 May 2024"  # Same date
        assert result[1].details == "MERCHANT2"

    @patch("parsers.aib_debit.pdfplumber")
    def test_extracts_transaction_with_reference_number(self, mock_pdfplumber):
        """Extracts transaction with reference number on following line."""
        # Arrange
        mock_pdf = Mock()
        mock_page = Mock()
        
        mock_page.extract_words.return_value = [
            {'text': 'Debit', 'x0': 250, 'x1': 300, 'top': 100},
            {'text': 'Credit', 'x0': 350, 'x1': 400, 'top': 100},
            {'text': 'Balance', 'x0': 450, 'x1': 500, 'top': 100},
            {'text': '5', 'x0': 50, 'x1': 70, 'top': 150},
            {'text': 'Jun', 'x0': 75, 'x1': 100, 'top': 150},
            {'text': '2024', 'x0': 105, 'x1': 140, 'top': 150},
            {'text': 'PAYMENT', 'x0': 150, 'x1': 220, 'top': 150},
            {'text': '200.00', 'x0': 280, 'x1': 330, 'top': 150},  # Debit
            {'text': '4800.00', 'x0': 460, 'x1': 520, 'top': 150},
            # Reference on next line
            {'text': 'IE12345678901234', 'x0': 150, 'x1': 300, 'top': 180},
        ]
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert len(result) == 1
        assert result[0].amount == 200.00
        assert result[0].reference == "IE12345678901234"

    @patch("parsers.aib_debit.pdfplumber")
    def test_returns_empty_list_when_no_column_headers_found(self, mock_pdfplumber):
        """Returns empty list when column headers cannot be identified."""
        # Arrange
        mock_pdf = Mock()
        mock_page = Mock()
        
        # No Debit/Credit headers
        mock_page.extract_words.return_value = [
            {'text': 'Some', 'x0': 50, 'x1': 90, 'top': 100},
            {'text': 'random', 'x0': 100, 'x1': 160, 'top': 100},
            {'text': 'text', 'x0': 165, 'x1': 200, 'top': 100},
        ]
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert result == []

    @patch("parsers.aib_debit.pdfplumber")
    def test_handles_exception_gracefully(self, mock_pdfplumber):
        """Exception during PDF processing returns empty list."""
        # Arrange
        mock_pdfplumber.open.side_effect = Exception("PDF error")
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert result == []

    @patch("parsers.aib_debit.pdfplumber")
    def test_filters_out_footer_keywords(self, mock_pdfplumber):
        """Footer keywords are filtered out and not included in transactions."""
        # Arrange
        mock_pdf = Mock()
        mock_page = Mock()
        
        mock_page.extract_words.return_value = [
            {'text': 'Debit', 'x0': 250, 'x1': 300, 'top': 100},
            {'text': 'Credit', 'x0': 350, 'x1': 400, 'top': 100},
            {'text': 'Balance', 'x0': 450, 'x1': 500, 'top': 100},
            {'text': '15', 'x0': 50, 'x1': 70, 'top': 150},
            {'text': 'Jul', 'x0': 75, 'x1': 100, 'top': 150},
            {'text': '2024', 'x0': 105, 'x1': 140, 'top': 150},
            {'text': 'TRANSACTION', 'x0': 150, 'x1': 250, 'top': 150},
            {'text': '75.00', 'x0': 280, 'x1': 330, 'top': 150},
            {'text': '4925.00', 'x0': 460, 'x1': 520, 'top': 150},
            # Footer text
            {'text': 'Thank', 'x0': 50, 'x1': 100, 'top': 700},
            {'text': 'you', 'x0': 105, 'x1': 130, 'top': 700},
            {'text': 'for', 'x0': 135, 'x1': 160, 'top': 700},
            {'text': 'banking', 'x0': 165, 'x1': 230, 'top': 700},
        ]
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
        
        # Act
        parser = AIBDebitParser()
        result = parser.extract_transactions(Path("dummy.pdf"))
        
        # Assert
        assert len(result) == 1
        assert result[0].details == "TRANSACTION"
        # Footer should not create a transaction
