"""Parser for AIB debit account statements."""

import re
from pathlib import Path

from pypdf import PdfReader

from .base import StatementParser


class AIBDebitParser:
    """Parser for AIB Personal Bank Account (debit) statements."""
    
    name = "AIB Debit Account"
    
    def can_parse(self, pdf_text: str) -> bool:
        """Check if this is an AIB debit account statement."""
        return (
            "Statement of Account" in pdf_text
            and "Personal Bank Account" in pdf_text
            and "Date of Statement" in pdf_text
        )
    
    def extract_dates(self, pdf_path: Path) -> tuple[str, str] | None:
        """
        Extract start and end dates from an AIB debit account statement.
        
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
            balance_forward_pattern = r'(\d{1,2}\s+\w{3}\s+\d{4})\s+BALANCE FORWARD'
            
            for page in reader.pages:
                page_text = page.extract_text()
                if not page_text:
                    continue
                
                balance_forward_match = re.search(balance_forward_pattern, page_text)
                if balance_forward_match:
                    start_date = balance_forward_match.group(1)
                    break
            
            # STRATEGY 2: Fallback to first transaction date
            if not start_date:
                date_pattern = r'(\d{1,2}\s+\w{3}\s+\d{4})'
                
                for page in reader.pages:
                    page_text = page.extract_text()
                    if not page_text:
                        continue
                    
                    matches = re.finditer(date_pattern, page_text)
                    for match in matches:
                        candidate_date = match.group(1)
                        line_context = page_text[max(0, match.start()-50):match.end()+150]
                        
                        if 'Date of Statement' in line_context:
                            continue
                        if 'Date Details' in line_context and 'Debit' not in line_context:
                            continue
                        
                        start_date = candidate_date
                        break
                    
                    if start_date:
                        break
            
            # Last resort: use end date as start date
            if not start_date:
                start_date = end_date
            
            return (start_date, end_date)
        
        except Exception:
            return None


# Auto-register parser instance
_parser = AIBDebitParser()
from .registry import register_parser
register_parser(_parser)
