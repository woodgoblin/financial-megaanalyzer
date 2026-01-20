"""Tests for parser registry and auto-detection."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from parsers.registry import register_parser, parse_statement, get_registered_parsers
from parsers.aib_debit import AIBDebitParser
from parsers.aib_credit import AIBCreditParser


class TestParserRegistry:
    """Tests for parser registration."""

    def test_register_parser_adds_to_list(self):
        """Registering a parser adds it to the registered parsers list."""
        # Arrange
        parser = AIBDebitParser()
        initial_count = len(get_registered_parsers())

        # Act
        register_parser(parser)
        registered = get_registered_parsers()

        # Assert
        assert len(registered) == initial_count + 1
        assert parser in registered

    def test_get_registered_parsers_returns_copy(self):
        """get_registered_parsers() returns a copy, not the original list."""
        # Arrange
        registered = get_registered_parsers()
        original_length = len(registered)

        # Act
        copy_list = get_registered_parsers()
        copy_list.append("not a parser")

        # Assert
        assert len(get_registered_parsers()) == original_length


class TestParseStatementAutoDetection:
    """Tests for automatic parser detection and parsing."""

    @patch("parsers.aib_debit.PdfReader")
    @patch("parsers.registry.PdfReader")
    def test_debit_parser_selected_for_debit_statement(
        self, mock_registry_reader, mock_debit_reader
    ):
        """Debit parser is selected when PDF matches debit statement format."""
        # Arrange
        mock_reader = Mock()
        mock_registry_reader.return_value = mock_reader
        mock_debit_reader.return_value = mock_reader

        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Statement of Account with Allied Irish Banks, p.l.c.
        Personal Bank Account
        Date of Statement
        31 Dec 2024
        1 Dec 2024 BALANCE FORWARD 1000.00
        """
        mock_reader.pages = [mock_page]

        # Act
        result = parse_statement(Path("debit.pdf"))

        # Assert
        assert result is not None
        start_date, end_date, parser_name = result
        assert parser_name == "AIB Debit Account"
        assert start_date == "1 Dec 2024"
        assert end_date == "31 Dec 2024"

    @patch("parsers.aib_credit.PdfReader")
    @patch("parsers.registry.PdfReader")
    def test_credit_parser_selected_for_credit_statement(
        self, mock_registry_reader, mock_credit_reader
    ):
        """Credit parser is selected when PDF matches credit statement format."""
        # Arrange
        mock_reader = Mock()
        mock_registry_reader.return_value = mock_reader
        mock_credit_reader.return_value = mock_reader

        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Credit Limit: €5,000.00
        Account Statement - 11th January, 2026
        13 Dec 15 Dec MERCHANT 50.00
        """
        mock_reader.pages = [mock_page]

        # Act
        result = parse_statement(Path("credit.pdf"))

        # Assert
        assert result is not None
        start_date, end_date, parser_name = result
        assert parser_name == "AIB Credit Card"
        assert end_date == "11 Jan 2026"

    @patch("parsers.registry.PdfReader")
    def test_returns_none_when_no_parser_matches(self, mock_reader_class):
        """Returns None when no registered parser can handle the PDF."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader

        mock_page = Mock()
        mock_page.extract_text.return_value = (
            "Random PDF content that matches no parser"
        )
        mock_reader.pages = [mock_page]

        # Act
        result = parse_statement(Path("unknown.pdf"))

        # Assert
        assert result is None

    @patch("parsers.registry.PdfReader")
    def test_returns_none_when_pdf_has_no_pages(self, mock_reader_class):
        """Returns None when PDF has no pages."""
        # Arrange
        mock_reader = Mock()
        mock_reader.pages = []
        mock_reader_class.return_value = mock_reader

        # Act
        result = parse_statement(Path("empty.pdf"))

        # Assert
        assert result is None

    @patch("parsers.registry.PdfReader")
    def test_returns_none_when_first_page_is_empty(self, mock_reader_class):
        """Returns None when first page has no extractable text."""
        # Arrange
        mock_reader = Mock()
        mock_page = Mock()
        mock_page.extract_text.return_value = ""
        mock_reader.pages = [mock_page]
        mock_reader_class.return_value = mock_reader

        # Act
        result = parse_statement(Path("empty_page.pdf"))

        # Assert
        assert result is None

    @patch("parsers.registry.PdfReader")
    def test_handles_exception_gracefully(self, mock_reader_class):
        """Exception during PDF reading returns None."""
        # Arrange
        mock_reader_class.side_effect = Exception("PDF error")

        # Act
        result = parse_statement(Path("bad.pdf"))

        # Assert
        assert result is None

    @patch("parsers.aib_debit.PdfReader")
    @patch("parsers.registry.PdfReader")
    def test_tries_parsers_in_registration_order(
        self, mock_registry_reader, mock_debit_reader
    ):
        """Parsers are tried in the order they were registered."""
        # Arrange
        mock_reader = Mock()
        mock_registry_reader.return_value = mock_reader
        mock_debit_reader.return_value = mock_reader

        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Statement of Account with Allied Irish Banks, p.l.c.
        Personal Bank Account
        Date of Statement
        31 Dec 2024
        1 Dec 2024 BALANCE FORWARD 1000.00
        """
        mock_reader.pages = [mock_page]

        # Act
        result = parse_statement(Path("debit.pdf"))

        # Assert
        assert result is not None
        # Should match debit parser (registered first via imports)
        assert result[2] == "AIB Debit Account"

    @patch("parsers.registry.PdfReader")
    def test_returns_none_when_parser_extract_dates_returns_none(
        self, mock_reader_class
    ):
        """Returns None when parser can_parse() matches but extract_dates() returns None."""
        # Arrange
        mock_reader = Mock()
        mock_reader_class.return_value = mock_reader

        mock_page = Mock()
        mock_page.extract_text.return_value = """
        Statement of Account with Allied Irish Banks, p.l.c.
        Personal Bank Account
        Date of Statement
        """
        mock_reader.pages = [mock_page]

        # Act
        result = parse_statement(Path("incomplete.pdf"))

        # Assert
        assert result is None
