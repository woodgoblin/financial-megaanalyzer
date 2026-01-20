"""Analyze AIB statement dates and generate summary report."""

import hashlib
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, Field
from pypdf import PdfReader


class StatementInfo(BaseModel):
    """Information about a single statement file."""
    
    file_name: str
    file_path: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    start_date_parsed: Optional[datetime] = None
    end_date_parsed: Optional[datetime] = None
    modified_timestamp: datetime
    file_signature: str
    error: Optional[str] = None


class StatementBreak(BaseModel):
    """Information about a gap between consecutive statements."""
    
    previous_file: str
    previous_end_date: str
    next_file: str
    next_start_date: str
    gap_days: int


class DuplicateGroup(BaseModel):
    """Group of duplicate files with the same content."""
    
    signature: str
    files: list[str] = Field(default_factory=list)


class AnalysisSummary(BaseModel):
    """Summary analysis of all statements."""
    
    total_files: int
    continuous_period_start: str
    continuous_period_end: str
    total_days_covered: int
    duplicates: list[DuplicateGroup] = Field(default_factory=list)
    breaks: list[StatementBreak] = Field(default_factory=list)


class StatementsAnalysis(BaseModel):
    """Complete analysis of AIB statements."""
    
    statements: list[StatementInfo] = Field(default_factory=list)
    summary: AnalysisSummary


def compute_file_signature(pdf_path: Path) -> str:
    """
    Compute SHA256 hash of file content to identify duplicates.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Hex string of the file's SHA256 hash
    """
    sha256_hash = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def extract_statement_dates(pdf_path: Path) -> tuple[str, str] | None:
    """
    Extract start and end dates from a bank statement PDF.
    
    Uses a two-strategy approach:
    1. Primary: Look for "BALANCE FORWARD" date (true statement start)
    2. Fallback: Look for first transaction date
    
    Returns:
        Tuple of (start_date, end_date) as strings in 'DD MMM YYYY' format,
        or None if dates cannot be extracted.
    """
    try:
        reader = PdfReader(pdf_path)
        
        # Extract end date from last non-empty page
        end_date = None
        for page in reversed(reader.pages):
            page_text = page.extract_text()
            if not page_text or len(page_text.strip()) < 50:
                continue
            
            statement_date_match = re.search(
                r'Date of Statement\s+(\d{1,2}\s+\w{3}\s+\d{4})',
                page_text
            )
            
            if statement_date_match:
                end_date = statement_date_match.group(1)
                break
        
        if not end_date:
            return None
        
        # Extract start date using two-strategy approach
        start_date = None
        
        # STRATEGY 1: Look for BALANCE FORWARD date (primary method)
        # This represents the actual statement period start date
        balance_forward_pattern = r'(\d{1,2}\s+\w{3}\s+\d{4})\s+BALANCE FORWARD'
        
        for page in reader.pages:
            page_text = page.extract_text()
            if not page_text:
                continue
            
            balance_forward_match = re.search(balance_forward_pattern, page_text)
            if balance_forward_match:
                start_date = balance_forward_match.group(1)
                break
        
        # STRATEGY 2: Fallback to first transaction date (legacy behavior)
        # Used when BALANCE FORWARD date is not found or extracted
        if not start_date:
            date_pattern = r'(\d{1,2}\s+\w{3}\s+\d{4})'
            
            for page in reader.pages:
                page_text = page.extract_text()
                if not page_text:
                    continue
                
                # Skip dates that are clearly headers
                matches = re.finditer(date_pattern, page_text)
                for match in matches:
                    candidate_date = match.group(1)
                    # Get context around the match
                    line_context = page_text[max(0, match.start()-50):match.end()+150]
                    
                    # Skip if it's in the header section or part of "Date of Statement"
                    if 'Date of Statement' in line_context:
                        continue
                    if 'Date Details' in line_context and 'Debit' not in line_context:
                        continue
                    
                    # Found a valid transaction date
                    start_date = candidate_date
                    break
                
                if start_date:
                    break
        
        # Last resort: use end date as start date
        if not start_date:
            start_date = end_date
        
        return (start_date, end_date)
    
    except Exception as e:
        print(f"Error processing {pdf_path.name}: {e}")
        return None


def parse_date(date_str: str) -> datetime:
    """Parse date string in format 'DD MMM YYYY' to datetime."""
    return datetime.strptime(date_str, '%d %b %Y')


def analyze_aib_statements(statements_dir: Path) -> Optional[StatementsAnalysis]:
    """
    Analyze all AIB statement PDFs in a directory.
    
    Args:
        statements_dir: Path to directory containing statement PDFs
        
    Returns:
        StatementsAnalysis object with complete analysis, or None if directory not found
    """
    if not statements_dir.exists():
        print(f"Directory not found: {statements_dir}")
        return None
    
    # Collect all statement information
    statements = []
    signature_map = {}
    
    pdf_files = []
    for pdf_path in statements_dir.glob('*.pdf'):
        mod_time = pdf_path.stat().st_mtime
        pdf_files.append((pdf_path, mod_time))
    
    pdf_files.sort(key=lambda x: x[1])
    
    for pdf_path, mod_time in pdf_files:
        dates = extract_statement_dates(pdf_path)
        mod_datetime = datetime.fromtimestamp(mod_time)
        signature = compute_file_signature(pdf_path)
        
        if dates:
            start_date, end_date = dates
            start_parsed = parse_date(start_date)
            end_parsed = parse_date(end_date)
            
            statement_info = StatementInfo(
                file_name=pdf_path.name,
                file_path=str(pdf_path),
                start_date=start_date,
                end_date=end_date,
                start_date_parsed=start_parsed,
                end_date_parsed=end_parsed,
                modified_timestamp=mod_datetime,
                file_signature=signature,
                error=None
            )
            
            statements.append(statement_info)
            
            if signature not in signature_map:
                signature_map[signature] = []
            signature_map[signature].append(pdf_path.name)
        else:
            statement_info = StatementInfo(
                file_name=pdf_path.name,
                file_path=str(pdf_path),
                start_date=None,
                end_date=None,
                start_date_parsed=None,
                end_date_parsed=None,
                modified_timestamp=mod_datetime,
                file_signature=signature,
                error="Could not extract dates from PDF"
            )
            
            statements.append(statement_info)
    
    if not statements:
        return StatementsAnalysis(
            statements=[],
            summary=AnalysisSummary(
                total_files=0,
                continuous_period_start="N/A",
                continuous_period_end="N/A",
                total_days_covered=0
            )
        )
    
    # Sort statements by start date for analysis (only valid ones)
    valid_statements = [s for s in statements if s.error is None]
    
    if not valid_statements:
        return StatementsAnalysis(
            statements=statements,
            summary=AnalysisSummary(
                total_files=0,
                continuous_period_start="N/A",
                continuous_period_end="N/A",
                total_days_covered=0
            )
        )
    
    statements_by_date = sorted(valid_statements, key=lambda s: s.start_date_parsed)
    
    # Find duplicates (signatures with multiple files)
    duplicates = []
    for signature, files in signature_map.items():
        if len(files) > 1:
            duplicates.append(DuplicateGroup(signature=signature, files=files))
    
    # Find breaks in statement continuity
    breaks = []
    for i in range(len(statements_by_date) - 1):
        current = statements_by_date[i]
        next_stmt = statements_by_date[i + 1]
        
        gap_days = (next_stmt.start_date_parsed - current.end_date_parsed).days
        
        # A break is when the gap is more than 1 day
        if gap_days > 1:
            breaks.append(StatementBreak(
                previous_file=current.file_name,
                previous_end_date=current.end_date,
                next_file=next_stmt.file_name,
                next_start_date=next_stmt.start_date,
                gap_days=gap_days
            ))
    
    # Calculate continuous period
    first_stmt = statements_by_date[0]
    last_stmt = statements_by_date[-1]
    total_days = (last_stmt.end_date_parsed - first_stmt.start_date_parsed).days
    
    summary = AnalysisSummary(
        total_files=len(valid_statements),
        continuous_period_start=first_stmt.start_date,
        continuous_period_end=last_stmt.end_date,
        total_days_covered=total_days,
        duplicates=duplicates,
        breaks=breaks
    )
    
    return StatementsAnalysis(statements=statements, summary=summary)


def main():
    """Analyze AIB statements and print results."""
    if len(sys.argv) > 1:
        statements_dir = Path(sys.argv[1])
    else:
        statements_dir = Path('../statements_raw/aib/debit')
    
    analysis = analyze_aib_statements(statements_dir)
    
    if not analysis:
        return
    
    print("=" * 100)
    print(f"AIB STATEMENTS ANALYSIS: {statements_dir}")
    print("=" * 100)
    print()
    
    # Print summary
    print("SUMMARY")
    print("-" * 100)
    print(f"Total Files:          {analysis.summary.total_files}")
    print(f"Continuous Period:    {analysis.summary.continuous_period_start} -> "
          f"{analysis.summary.continuous_period_end}")
    print(f"Total Days Covered:   {analysis.summary.total_days_covered}")
    print()
    
    # Print duplicates
    if analysis.summary.duplicates:
        print("DUPLICATE FILES")
        print("-" * 100)
        for dup in analysis.summary.duplicates:
            print(f"Signature: {dup.signature[:16]}...")
            for file_name in dup.files:
                print(f"  - {file_name}")
        print()
    else:
        print("DUPLICATE FILES: None found")
        print()
    
    # Print breaks
    if analysis.summary.breaks:
        print("STATEMENT BREAKS (gaps > 1 day)")
        print("-" * 100)
        for brk in analysis.summary.breaks:
            print(f"Gap of {brk.gap_days} days:")
            print(f"  Previous: {brk.previous_file} ends {brk.previous_end_date}")
            print(f"  Next:     {brk.next_file} starts {brk.next_start_date}")
        print()
    else:
        print("STATEMENT BREAKS: None found (continuous coverage)")
        print()
    
    # Print all statements
    print("ALL STATEMENTS (sorted by modification time)")
    print("-" * 100)
    print(f"{'File Name':<30} {'Start Date':<15} {'End Date':<15} {'Modified':<20}")
    print("-" * 100)
    
    for stmt in analysis.statements:
        mod_str = stmt.modified_timestamp.strftime('%Y-%m-%d %H:%M:%S')
        if stmt.error:
            print(f"{stmt.file_name:<30} {'ERROR':<15} {'ERROR':<15} {mod_str:<20}")
            print(f"  -> {stmt.error}")
        else:
            print(f"{stmt.file_name:<30} {stmt.start_date:<15} {stmt.end_date:<15} {mod_str:<20}")
    
    print("=" * 100)


if __name__ == "__main__":
    main()
