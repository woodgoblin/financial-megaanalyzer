"""Tests for statement file renamer script."""

import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from rename_statements import (
    format_date_for_filename,
    sanitize_parser_name,
    rename_statements,
)
from models import StatementInfo, StatementsAnalysis, AnalysisSummary
from analyze_aib_dates import analyze_statements


class TestFormatDateForFilename:
    """Tests for date formatting function."""

    def test_formats_valid_date_correctly(self):
        """Valid date string is formatted as MMMYYYY."""
        # Arrange
        date_str = "19 Jan 2026"

        # Act
        result = format_date_for_filename(date_str)

        # Assert
        assert result == "Jan2026"

    def test_formats_year_correctly(self):
        """Year is included in the formatted string."""
        # Arrange
        date_str = "5 Jul 2025"

        # Act
        result = format_date_for_filename(date_str)

        # Assert
        assert result == "Jul2025"

    def test_handles_different_years(self):
        """Different years are formatted correctly."""
        # Arrange
        date_str = "25 Dec 2024"

        # Act
        result = format_date_for_filename(date_str)

        # Assert
        assert result == "Dec2024"

    def test_handles_invalid_date_gracefully(self):
        """Invalid date string returns fallback format."""
        # Arrange
        date_str = "Invalid Date"

        # Act
        result = format_date_for_filename(date_str)

        # Assert
        assert result == "Unknown"


class TestSanitizeParserName:
    """Tests for parser name sanitization."""

    def test_replaces_spaces_with_underscores(self):
        """Spaces in parser name are replaced with underscores."""
        # Arrange
        parser_name = "AIB Debit Account"

        # Act
        result = sanitize_parser_name(parser_name)

        # Assert
        assert result == "AIB_Debit_Account"

    def test_replaces_hyphens_with_underscores(self):
        """Hyphens in parser name are replaced with underscores."""
        # Arrange
        parser_name = "Revolut-Debit-Account"

        # Act
        result = sanitize_parser_name(parser_name)

        # Assert
        assert result == "Revolut_Debit_Account"

    def test_handles_name_without_spaces(self):
        """Parser name without spaces remains unchanged."""
        # Arrange
        parser_name = "AIBDebit"

        # Act
        result = sanitize_parser_name(parser_name)

        # Assert
        assert result == "AIBDebit"


class TestRenameStatements:
    """Tests for main renaming function."""

    @patch("rename_statements.analyze_statements")
    def test_creates_output_directory(self, mock_analyze):
        """Output directory is created if it doesn't exist."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input"
            output_dir = Path(tmpdir) / "output"
            input_dir.mkdir()

            # Create a dummy PDF
            pdf_file = input_dir / "test.pdf"
            pdf_file.write_bytes(b"dummy pdf content")

            # Mock analysis result
            stmt_info = StatementInfo(
                file_name="test.pdf",
                file_path=str(pdf_file),
                start_date="1 Jan 2024",
                end_date="31 Jan 2024",
                start_date_parsed=datetime(2024, 1, 1),
                end_date_parsed=datetime(2024, 1, 31),
                modified_timestamp=datetime(2024, 1, 1),
                file_signature="abc123",
                parser_name="Test Parser",
            )

            analysis = StatementsAnalysis(
                statements=[stmt_info],
                summary=AnalysisSummary(
                    total_files=1,
                    continuous_period_start="1 Jan 2024",
                    continuous_period_end="31 Jan 2024",
                    total_days_covered=30,
                    duplicates=[],
                    breaks=[],
                ),
            )
            mock_analyze.return_value = analysis

            # Act
            stats = rename_statements(input_dir, output_dir)

            # Assert
            assert output_dir.exists()
            assert stats["copied"] == 1

    @patch("rename_statements.analyze_statements")
    def test_copies_file_with_correct_name(self, mock_analyze):
        """File is copied with correctly formatted name."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input"
            output_dir = Path(tmpdir) / "output"
            input_dir.mkdir()

            pdf_file = input_dir / "test.pdf"
            pdf_file.write_bytes(b"dummy pdf content")

            stmt_info = StatementInfo(
                file_name="test.pdf",
                file_path=str(pdf_file),
                start_date="5 Jul 2025",
                end_date="19 Jan 2026",
                start_date_parsed=datetime(2025, 7, 5),
                end_date_parsed=datetime(2026, 1, 19),
                modified_timestamp=datetime(2024, 1, 1),
                file_signature="abc123",
                parser_name="AIB Debit Account",
            )

            analysis = StatementsAnalysis(
                statements=[stmt_info],
                summary=AnalysisSummary(
                    total_files=1,
                    continuous_period_start="5 Jul 2025",
                    continuous_period_end="19 Jan 2026",
                    total_days_covered=198,
                    duplicates=[],
                    breaks=[],
                ),
            )
            mock_analyze.return_value = analysis

            # Act
            stats = rename_statements(input_dir, output_dir)

            # Assert
            expected_name = "AIB_Debit_Account_from_Jul2025_to_Jan2026.pdf"
            expected_path = output_dir / expected_name
            assert expected_path.exists()
            assert expected_path.read_bytes() == b"dummy pdf content"
            assert stats["copied"] == 1

    @patch("rename_statements.analyze_statements")
    def test_skips_files_with_errors(self, mock_analyze):
        """Files with errors are skipped."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input"
            output_dir = Path(tmpdir) / "output"
            input_dir.mkdir()

            pdf_file = input_dir / "bad.pdf"
            pdf_file.write_bytes(b"bad content")

            stmt_info = StatementInfo(
                file_name="bad.pdf",
                file_path=str(pdf_file),
                modified_timestamp=datetime(2024, 1, 1),
                file_signature="bad123",
                error="Could not extract dates",
            )

            analysis = StatementsAnalysis(
                statements=[stmt_info],
                summary=AnalysisSummary(
                    total_files=1,
                    continuous_period_start="N/A",
                    continuous_period_end="N/A",
                    total_days_covered=0,
                    duplicates=[],
                    breaks=[],
                ),
            )
            mock_analyze.return_value = analysis

            # Act
            stats = rename_statements(input_dir, output_dir)

            # Assert
            assert stats["copied"] == 0
            assert stats["skipped"] == 1
            assert not any(output_dir.iterdir()) if output_dir.exists() else True

    @patch("rename_statements.analyze_statements")
    def test_skips_files_without_parser_name(self, mock_analyze):
        """Files without parser name are skipped."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input"
            output_dir = Path(tmpdir) / "output"
            input_dir.mkdir()

            pdf_file = input_dir / "test.pdf"
            pdf_file.write_bytes(b"content")

            stmt_info = StatementInfo(
                file_name="test.pdf",
                file_path=str(pdf_file),
                start_date="1 Jan 2024",
                end_date="31 Jan 2024",
                start_date_parsed=datetime(2024, 1, 1),
                end_date_parsed=datetime(2024, 1, 31),
                modified_timestamp=datetime(2024, 1, 1),
                file_signature="abc123",
                parser_name=None,
            )

            analysis = StatementsAnalysis(
                statements=[stmt_info],
                summary=AnalysisSummary(
                    total_files=1,
                    continuous_period_start="1 Jan 2024",
                    continuous_period_end="31 Jan 2024",
                    total_days_covered=30,
                    duplicates=[],
                    breaks=[],
                ),
            )
            mock_analyze.return_value = analysis

            # Act
            stats = rename_statements(input_dir, output_dir)

            # Assert
            assert stats["copied"] == 0
            assert stats["skipped"] == 1

    @patch("rename_statements.analyze_statements")
    def test_handles_duplicate_filenames(self, mock_analyze):
        """Duplicate filenames are handled with counter suffix."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input"
            output_dir = Path(tmpdir) / "output"
            input_dir.mkdir()
            output_dir.mkdir()

            pdf1 = input_dir / "test1.pdf"
            pdf2 = input_dir / "test2.pdf"
            pdf1.write_bytes(b"content1")
            pdf2.write_bytes(b"content2")

            # Both files have same dates and parser (would produce same filename)
            stmt1 = StatementInfo(
                file_name="test1.pdf",
                file_path=str(pdf1),
                start_date="1 Jan 2024",
                end_date="31 Jan 2024",
                start_date_parsed=datetime(2024, 1, 1),
                end_date_parsed=datetime(2024, 1, 31),
                modified_timestamp=datetime(2024, 1, 1),
                file_signature="sig1",
                parser_name="Test Parser",
            )

            stmt2 = StatementInfo(
                file_name="test2.pdf",
                file_path=str(pdf2),
                start_date="1 Jan 2024",
                end_date="31 Jan 2024",
                start_date_parsed=datetime(2024, 1, 1),
                end_date_parsed=datetime(2024, 1, 31),
                modified_timestamp=datetime(2024, 1, 2),
                file_signature="sig2",
                parser_name="Test Parser",
            )

            analysis = StatementsAnalysis(
                statements=[stmt1, stmt2],
                summary=AnalysisSummary(
                    total_files=2,
                    continuous_period_start="1 Jan 2024",
                    continuous_period_end="31 Jan 2024",
                    total_days_covered=30,
                    duplicates=[],
                    breaks=[],
                ),
            )
            mock_analyze.return_value = analysis

            # Act
            stats = rename_statements(input_dir, output_dir)

            # Assert
            base_name = "Test_Parser_from_Jan2024_to_Jan2024.pdf"
            assert (output_dir / base_name).exists()
            assert (output_dir / f"{base_name.replace('.pdf', '_1.pdf')}").exists()
            assert stats["copied"] == 2

    @patch("rename_statements.analyze_statements")
    def test_dry_run_does_not_copy_files(self, mock_analyze):
        """Dry run mode shows what would be done without copying."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input"
            output_dir = Path(tmpdir) / "output"
            input_dir.mkdir()

            pdf_file = input_dir / "test.pdf"
            pdf_file.write_bytes(b"content")

            stmt_info = StatementInfo(
                file_name="test.pdf",
                file_path=str(pdf_file),
                start_date="1 Jan 2024",
                end_date="31 Jan 2024",
                start_date_parsed=datetime(2024, 1, 1),
                end_date_parsed=datetime(2024, 1, 31),
                modified_timestamp=datetime(2024, 1, 1),
                file_signature="abc123",
                parser_name="Test Parser",
            )

            analysis = StatementsAnalysis(
                statements=[stmt_info],
                summary=AnalysisSummary(
                    total_files=1,
                    continuous_period_start="1 Jan 2024",
                    continuous_period_end="31 Jan 2024",
                    total_days_covered=30,
                    duplicates=[],
                    breaks=[],
                ),
            )
            mock_analyze.return_value = analysis

            # Act
            stats = rename_statements(input_dir, output_dir, dry_run=True)

            # Assert
            assert not output_dir.exists()
            assert stats["copied"] == 0

    @patch("rename_statements.analyze_statements")
    def test_uses_default_output_directory(self, mock_analyze):
        """Default output directory is input_dir/renamed."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input"
            input_dir.mkdir()

            pdf_file = input_dir / "test.pdf"
            pdf_file.write_bytes(b"content")

            stmt_info = StatementInfo(
                file_name="test.pdf",
                file_path=str(pdf_file),
                start_date="1 Jan 2024",
                end_date="31 Jan 2024",
                start_date_parsed=datetime(2024, 1, 1),
                end_date_parsed=datetime(2024, 1, 31),
                modified_timestamp=datetime(2024, 1, 1),
                file_signature="abc123",
                parser_name="Test Parser",
            )

            analysis = StatementsAnalysis(
                statements=[stmt_info],
                summary=AnalysisSummary(
                    total_files=1,
                    continuous_period_start="1 Jan 2024",
                    continuous_period_end="31 Jan 2024",
                    total_days_covered=30,
                    duplicates=[],
                    breaks=[],
                ),
            )
            mock_analyze.return_value = analysis

            # Act
            stats = rename_statements(input_dir)

            # Assert
            expected_output = input_dir / "renamed"
            assert expected_output.exists()
            assert stats["copied"] == 1

    @patch("rename_statements.analyze_statements")
    def test_handles_analysis_failure(self, mock_analyze):
        """Analysis failure returns error statistics."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input"
            input_dir.mkdir()

            mock_analyze.return_value = None

            # Act
            stats = rename_statements(input_dir)

            # Assert
            assert stats["errors"] == 1
            assert stats["copied"] == 0
