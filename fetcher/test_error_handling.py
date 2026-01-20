"""Tests for error handling in PDF processing."""

import tempfile
import time
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from analyze_aib_dates import analyze_statements


class TestErrorHandling:
    """Tests for handling PDF processing errors."""

    @patch("analyze_aib_dates.parse_statement")
    @patch("analyze_aib_dates.compute_file_signature")
    def test_failed_pdf_is_listed_in_output(self, mock_signature, mock_parse_statement):
        """Failed PDF files are included in statements list with error field populated."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            pdf1 = tmppath / "working.pdf"
            pdf1.write_bytes(b"content1")
            time.sleep(0.01)
            pdf2 = tmppath / "broken.pdf"
            pdf2.write_bytes(b"content2")

            mock_signature.side_effect = ["sig1", "sig2"]
            mock_parse_statement.side_effect = [
                ("1 Mar 2015", "31 Mar 2015", "Test Parser"),
                None,
            ]

            # Act
            result = analyze_statements(tmppath)

        # Assert
        assert result is not None
        assert len(result.statements) == 2

        working_stmt = [s for s in result.statements if s.file_name == "working.pdf"][0]
        assert working_stmt.error is None
        assert working_stmt.start_date == "1 Mar 2015"

        broken_stmt = [s for s in result.statements if s.file_name == "broken.pdf"][0]
        assert broken_stmt.error is not None
        assert broken_stmt.start_date is None
        assert broken_stmt.end_date is None

    @patch("analyze_aib_dates.parse_statement")
    @patch("analyze_aib_dates.compute_file_signature")
    def test_multiple_failed_pdfs_all_listed(
        self, mock_signature, mock_parse_statement
    ):
        """Multiple failed PDFs are all included in the output."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            pdf1 = tmppath / "fail1.pdf"
            pdf1.write_bytes(b"content1")
            time.sleep(0.01)
            pdf2 = tmppath / "fail2.pdf"
            pdf2.write_bytes(b"content2")
            time.sleep(0.01)
            pdf3 = tmppath / "fail3.pdf"
            pdf3.write_bytes(b"content3")

            mock_signature.side_effect = ["sig1", "sig2", "sig3"]
            mock_parse_statement.side_effect = [None, None, None]

            # Act
            result = analyze_statements(tmppath)

        # Assert
        assert result is not None
        assert len(result.statements) == 3
        assert all(stmt.error is not None for stmt in result.statements)

    @patch("analyze_aib_dates.parse_statement")
    @patch("analyze_aib_dates.compute_file_signature")
    def test_error_message_indicates_date_extraction_failure(
        self, mock_signature, mock_parse_statement
    ):
        """Error message clearly indicates date extraction failure."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            pdf = tmppath / "test.pdf"
            pdf.write_bytes(b"content")

            mock_signature.return_value = "sig1"
            mock_parse_statement.return_value = None

            # Act
            result = analyze_statements(tmppath)

        # Assert
        assert result is not None
        assert len(result.statements) == 1
        assert result.statements[0].error is not None
        assert "date" in result.statements[0].error.lower()

    @patch("analyze_aib_dates.parse_statement")
    @patch("analyze_aib_dates.compute_file_signature")
    def test_failed_pdfs_excluded_from_summary_calculations(
        self, mock_signature, mock_parse_statement
    ):
        """Failed PDFs are not included in period calculations but counted in total."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            pdf1 = tmppath / "valid.pdf"
            pdf1.write_bytes(b"content1")
            time.sleep(0.01)
            pdf2 = tmppath / "invalid.pdf"
            pdf2.write_bytes(b"content2")

            mock_signature.side_effect = ["sig1", "sig2"]
            mock_parse_statement.side_effect = [
                ("1 Apr 2014", "30 Apr 2014", "Test Parser"),
                None,
            ]

            # Act
            result = analyze_statements(tmppath)

        # Assert
        assert result is not None
        assert len(result.statements) == 2
        assert result.summary.continuous_period_start == "1 Apr 2014"
        assert result.summary.continuous_period_end == "30 Apr 2014"

    @patch("analyze_aib_dates.parse_statement")
    @patch("analyze_aib_dates.compute_file_signature")
    def test_failed_pdfs_not_included_in_duplicate_detection(
        self, mock_signature, mock_parse_statement
    ):
        """Failed PDFs with same signature are not flagged as duplicates."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            pdf1 = tmppath / "fail1.pdf"
            pdf1.write_bytes(b"content")
            time.sleep(0.01)
            pdf2 = tmppath / "fail2.pdf"
            pdf2.write_bytes(b"content")

            mock_signature.return_value = "same_sig"
            mock_parse_statement.return_value = None

            # Act
            result = analyze_statements(tmppath)

        # Assert
        assert result is not None
        assert len(result.statements) == 2
        assert all(stmt.error is not None for stmt in result.statements)
        assert len(result.summary.duplicates) == 0

    @patch("analyze_aib_dates.parse_statement")
    @patch("analyze_aib_dates.compute_file_signature")
    def test_mix_of_valid_and_failed_pdfs_processed_correctly(
        self, mock_signature, mock_parse_statement
    ):
        """Mix of valid and failed PDFs are all listed with appropriate fields."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            valid1 = tmppath / "valid1.pdf"
            valid1.write_bytes(b"v1")
            time.sleep(0.01)
            failed1 = tmppath / "failed1.pdf"
            failed1.write_bytes(b"f1")
            time.sleep(0.01)
            valid2 = tmppath / "valid2.pdf"
            valid2.write_bytes(b"v2")
            time.sleep(0.01)
            failed2 = tmppath / "failed2.pdf"
            failed2.write_bytes(b"f2")

            mock_signature.side_effect = ["sig1", "sig2", "sig3", "sig4"]
            mock_parse_statement.side_effect = [
                ("1 Jan 2013", "31 Jan 2013", "Test Parser"),
                None,
                ("1 Feb 2013", "28 Feb 2013", "Test Parser"),
                None,
            ]

            # Act
            result = analyze_statements(tmppath)

        # Assert
        assert result is not None
        assert len(result.statements) == 4

        valid_count = sum(1 for s in result.statements if s.error is None)
        failed_count = sum(1 for s in result.statements if s.error is not None)

        assert valid_count == 2
        assert failed_count == 2
