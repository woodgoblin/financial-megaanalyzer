"""Comprehensive tests for AIB statement analysis script."""

import tempfile
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO

from analyze_aib_dates import (
    compute_file_signature,
    parse_date,
    analyze_statements,
)
from models import (
    StatementInfo,
    StatementBreak,
    DuplicateGroup,
    AnalysisSummary,
    StatementsAnalysis,
)
from parsers import parse_statement


class TestComputeFileSignature:
    """Tests for SHA256 file signature computation."""

    def test_identical_files_produce_same_signature(self):
        """Two files with identical content produce the same SHA256 signature."""
        # Arrange
        content = b"This is test content for PDF file"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp1:
            tmp1.write(content)
            path1 = Path(tmp1.name)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp2:
            tmp2.write(content)
            path2 = Path(tmp2.name)
        
        try:
            # Act
            signature1 = compute_file_signature(path1)
            signature2 = compute_file_signature(path2)
            
            # Assert
            assert signature1 == signature2
            assert len(signature1) == 64  # SHA256 produces 64 hex characters
        finally:
            path1.unlink(missing_ok=True)
            path2.unlink(missing_ok=True)

    def test_different_files_produce_different_signatures(self):
        """Two files with different content produce different SHA256 signatures."""
        # Arrange
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp1:
            tmp1.write(b"Content A")
            path1 = Path(tmp1.name)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp2:
            tmp2.write(b"Content B")
            path2 = Path(tmp2.name)
        
        try:
            # Act
            signature1 = compute_file_signature(path1)
            signature2 = compute_file_signature(path2)
            
            # Assert
            assert signature1 != signature2
        finally:
            path1.unlink(missing_ok=True)
            path2.unlink(missing_ok=True)

    def test_signature_is_valid_hexadecimal_string(self):
        """File signature is a valid 64-character hexadecimal string."""
        # Arrange
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(b"Test content")
            path = Path(tmp.name)
        
        try:
            # Act
            signature = compute_file_signature(path)
            
            # Assert
            assert len(signature) == 64
            assert all(c in '0123456789abcdef' for c in signature)
        finally:
            path.unlink(missing_ok=True)


class TestParseDateFunction:
    """Tests for date string parsing."""

    def test_valid_date_string_is_parsed_correctly(self):
        """Valid date string in DD MMM YYYY format is correctly parsed to datetime."""
        # Arrange
        date_str = "5 Mar 2018"
        
        # Act
        result = parse_date(date_str)
        
        # Assert
        assert result.day == 5
        assert result.month == 3
        assert result.year == 2018

    def test_single_digit_day_is_parsed_correctly(self):
        """Date string with single-digit day is parsed correctly."""
        # Arrange
        date_str = "7 Feb 2017"
        
        # Act
        result = parse_date(date_str)
        
        # Assert
        assert result.day == 7
        assert result.month == 2
        assert result.year == 2017

    def test_invalid_date_format_raises_exception(self):
        """Invalid date format raises ValueError exception."""
        # Arrange
        invalid_date = "2018-03-05"
        
        # Act & Assert
        with pytest.raises(ValueError):
            parse_date(invalid_date)

    def test_invalid_month_abbreviation_raises_exception(self):
        """Invalid month abbreviation raises ValueError exception."""
        # Arrange
        invalid_date = "5 Xyz 2018"
        
        # Act & Assert
        with pytest.raises(ValueError):
            parse_date(invalid_date)


class TestPydanticModels:
    """Tests for Pydantic model validation and structure."""

    def test_statement_info_model_validates_required_fields(self):
        """StatementInfo model correctly validates all required fields."""
        # Arrange
        data = {
            "file_name": "test.pdf",
            "file_path": "/path/to/test.pdf",
            "start_date": "1 Jan 2018",
            "end_date": "31 Jan 2018",
            "start_date_parsed": datetime(2018, 1, 1),
            "end_date_parsed": datetime(2018, 1, 31),
            "modified_timestamp": datetime(2024, 1, 1),
            "file_signature": "abc123" * 10 + "abcd"
        }
        
        # Act
        statement = StatementInfo(**data)
        
        # Assert
        assert statement.file_name == "test.pdf"
        assert statement.start_date == "1 Jan 2018"
        assert statement.start_date_parsed.year == 2018

    def test_statement_break_model_stores_gap_information(self):
        """StatementBreak model correctly stores gap information between statements."""
        # Arrange
        data = {
            "previous_file": "statement1.pdf",
            "previous_end_date": "10 Mar 2017",
            "next_file": "statement2.pdf",
            "next_start_date": "14 Mar 2017",
            "gap_days": 4
        }
        
        # Act
        break_info = StatementBreak(**data)
        
        # Assert
        assert break_info.gap_days == 4
        assert break_info.previous_file == "statement1.pdf"
        assert break_info.next_file == "statement2.pdf"

    def test_duplicate_group_model_has_empty_files_list_by_default(self):
        """DuplicateGroup model correctly initializes with empty files list."""
        # Arrange & Act
        dup = DuplicateGroup(signature="abc123")
        
        # Assert
        assert dup.signature == "abc123"
        assert dup.files == []

    def test_analysis_summary_model_accepts_all_summary_data(self):
        """AnalysisSummary model correctly stores all summary statistics."""
        # Arrange
        dup = DuplicateGroup(signature="sig1", files=["file1.pdf", "file2.pdf"])
        brk = StatementBreak(
            previous_file="f1.pdf",
            previous_end_date="1 Feb 2016",
            next_file="f2.pdf",
            next_start_date="8 Feb 2016",
            gap_days=7
        )
        
        data = {
            "total_files": 10,
            "continuous_period_start": "1 Feb 2016",
            "continuous_period_end": "31 Jan 2017",
            "total_days_covered": 365,
            "duplicates": [dup],
            "breaks": [brk]
        }
        
        # Act
        summary = AnalysisSummary(**data)
        
        # Assert
        assert summary.total_files == 10
        assert len(summary.duplicates) == 1
        assert len(summary.breaks) == 1
        assert summary.duplicates[0].signature == "sig1"


class TestAnalyzeAibStatements:
    """Tests for the main analysis function."""

    def test_nonexistent_directory_returns_none(self):
        """Analyzing a non-existent directory correctly returns None."""
        # Arrange
        non_existent = Path("nonexistent_directory")
        
        # Act
        result = analyze_statements(non_existent)
        
        # Assert
        assert result is None

    def test_empty_directory_returns_analysis_with_zero_files(self):
        """Empty directory returns analysis with zero files and N/A dates."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            # Act
            result = analyze_statements(Path(tmpdir))
        
        # Assert
        assert result is not None
        assert result.summary.total_files == 0
        assert result.summary.continuous_period_start == "N/A"
        assert result.summary.continuous_period_end == "N/A"
        assert len(result.statements) == 0

    @patch('analyze_aib_dates.parse_statement')
    @patch('analyze_aib_dates.compute_file_signature')
    def test_duplicate_files_are_detected_correctly(
        self, mock_signature, mock_parse_statement
    ):
        """Duplicate files with same signature are correctly identified."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Create two dummy PDF files
            pdf1 = tmppath / "statement1.pdf"
            pdf2 = tmppath / "statement2.pdf"
            pdf1.write_bytes(b"content")
            pdf2.write_bytes(b"content")
            
            # Mock both files return same signature (duplicates)
            mock_signature.return_value = "same_signature_abc123"
            mock_parse_statement.return_value = ("1 Jun 2015", "30 Jun 2015", "Test Parser")
            
            # Act
            result = analyze_statements(tmppath)
        
        # Assert
        assert result is not None
        assert len(result.summary.duplicates) == 1
        assert len(result.summary.duplicates[0].files) == 2

    @patch('analyze_aib_dates.parse_statement')
    @patch('analyze_aib_dates.compute_file_signature')
    def test_statement_breaks_are_detected_when_gap_exceeds_one_day(
        self, mock_signature, mock_parse_statement
    ):
        """Gaps larger than 1 day between statements are correctly detected."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            pdf1 = tmppath / "statement1.pdf"
            pdf2 = tmppath / "statement2.pdf"
            pdf1.write_bytes(b"content1")
            pdf2.write_bytes(b"content2")
            
            mock_signature.side_effect = ["sig1", "sig2"]
            mock_parse_statement.side_effect = [
                ("1 Aug 2014", "10 Aug 2014", "Test Parser"),
                ("16 Aug 2014", "31 Aug 2014", "Test Parser")
            ]
            
            # Act
            result = analyze_statements(tmppath)
        
        # Assert
        assert result is not None
        assert len(result.summary.breaks) == 1
        assert result.summary.breaks[0].gap_days == 6

    @patch('analyze_aib_dates.parse_statement')
    @patch('analyze_aib_dates.compute_file_signature')
    def test_consecutive_statements_with_one_day_gap_have_no_break(
        self, mock_signature, mock_parse_statement
    ):
        """Consecutive statements with exactly 1-day gap show no break."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            pdf1 = tmppath / "statement1.pdf"
            pdf2 = tmppath / "statement2.pdf"
            pdf1.write_bytes(b"content1")
            pdf2.write_bytes(b"content2")
            
            mock_signature.side_effect = ["sig1", "sig2"]
            mock_parse_statement.side_effect = [
                ("1 May 2013", "15 May 2013", "Test Parser"),
                ("16 May 2013", "31 May 2013", "Test Parser")
            ]
            
            # Act
            result = analyze_statements(tmppath)
        
        # Assert
        assert result is not None
        assert len(result.summary.breaks) == 0

    @patch('analyze_aib_dates.parse_statement')
    @patch('analyze_aib_dates.compute_file_signature')
    def test_overlapping_statements_show_negative_gap(
        self, mock_signature, mock_parse_statement
    ):
        """Overlapping statements with next starting before previous ends show no break."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            pdf1 = tmppath / "statement1.pdf"
            pdf2 = tmppath / "statement2.pdf"
            pdf1.write_bytes(b"content1")
            pdf2.write_bytes(b"content2")
            
            mock_signature.side_effect = ["sig1", "sig2"]
            mock_parse_statement.side_effect = [
                ("1 Nov 2012", "20 Nov 2012", "Test Parser"),
                ("15 Nov 2012", "30 Nov 2012", "Test Parser")
            ]
            
            # Act
            result = analyze_statements(tmppath)
        
        # Assert
        assert result is not None
        assert len(result.summary.breaks) == 0

    @patch('analyze_aib_dates.parse_statement')
    @patch('analyze_aib_dates.compute_file_signature')
    def test_total_days_covered_calculated_from_first_to_last_statement(
        self, mock_signature, mock_parse_statement
    ):
        """Total days covered is correctly calculated from first to last statement."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            pdf1 = tmppath / "statement1.pdf"
            pdf1.write_bytes(b"content1")
            
            mock_signature.return_value = "sig1"
            mock_parse_statement.return_value = ("1 Apr 2011", "30 Apr 2011", "Test Parser")
            
            # Act
            result = analyze_statements(tmppath)
        
        # Assert
        assert result is not None
        assert result.summary.total_days_covered == 29

    @patch('analyze_aib_dates.parse_statement')
    @patch('analyze_aib_dates.compute_file_signature')
    def test_statements_with_unparseable_dates_are_included_with_error(
        self, mock_signature, mock_parse_statement
    ):
        """Statements that return None for dates are included with error information."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            pdf1 = tmppath / "valid.pdf"
            pdf2 = tmppath / "invalid.pdf"
            pdf1.write_bytes(b"content1")
            pdf2.write_bytes(b"content2")
            
            mock_signature.side_effect = ["sig1", "sig2"]
            mock_parse_statement.side_effect = [
                ("1 Sep 2010", "30 Sep 2010", "Test Parser"),
                None
            ]
            
            # Act
            result = analyze_statements(tmppath)
        
        # Assert
        assert result is not None
        assert len(result.statements) == 2
        assert result.statements[0].error is None
        assert result.statements[1].error is not None
        assert "Could not extract dates" in result.statements[1].error

    @patch('analyze_aib_dates.parse_statement')
    @patch('analyze_aib_dates.compute_file_signature')
    def test_statements_are_sorted_by_modification_time_in_output(
        self, mock_signature, mock_parse_statement
    ):
        """Statements list preserves modification time order from directory scan."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            pdf1 = tmppath / "old.pdf"
            pdf1.write_bytes(b"content1")
            
            import time
            time.sleep(0.01)
            
            pdf2 = tmppath / "new.pdf"
            pdf2.write_bytes(b"content2")
            
            mock_signature.side_effect = ["sig1", "sig2"]
            mock_parse_statement.side_effect = [
                ("1 Jul 2009", "31 Jul 2009", "Test Parser"),
                ("1 Jun 2009", "30 Jun 2009", "Test Parser")
            ]
            
            # Act
            result = analyze_statements(tmppath)
        
        # Assert
        assert result is not None
        assert len(result.statements) == 2
        assert result.statements[0].file_name == "old.pdf"


class TestEdgeCasesAndNegativeScenarios:
    """Tests for edge cases and negative scenarios handled by the code."""


    def test_parse_date_with_empty_string_raises_exception(self):
        """Empty string passed to parse_date raises ValueError."""
        # Arrange
        empty_string = ""
        
        # Act & Assert
        with pytest.raises(ValueError):
            parse_date(empty_string)

    def test_compute_signature_with_empty_file(self):
        """Empty file produces valid SHA256 signature."""
        # Arrange
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            path = Path(tmp.name)
        
        try:
            # Act
            signature = compute_file_signature(path)
            
            # Assert
            assert len(signature) == 64
            assert all(c in '0123456789abcdef' for c in signature)
            assert signature == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        finally:
            path.unlink(missing_ok=True)

    @patch('analyze_aib_dates.parse_statement')
    @patch('analyze_aib_dates.compute_file_signature')
    def test_multiple_statements_same_dates_no_duplicates_flagged(
        self, mock_signature, mock_parse_statement
    ):
        """Multiple statements with same dates but different content not flagged as duplicates."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            pdf1 = tmppath / "statement1.pdf"
            pdf2 = tmppath / "statement2.pdf"
            pdf1.write_bytes(b"content1")
            pdf2.write_bytes(b"different_content")
            
            mock_signature.side_effect = ["sig1", "sig2_different"]
            mock_parse_statement.side_effect = [
                ("1 Dec 2008", "31 Dec 2008", "Test Parser"),
                ("1 Dec 2008", "31 Dec 2008", "Test Parser")
            ]
            
            # Act
            result = analyze_statements(tmppath)
        
        # Assert
        assert result is not None
        assert len(result.summary.duplicates) == 0

