"""Pydantic models for statement analysis."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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
    parser_name: Optional[str] = None


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
    """Complete analysis of statements."""

    statements: list[StatementInfo] = Field(default_factory=list)
    summary: AnalysisSummary


class Transaction(BaseModel):
    """A single transaction record from a statement."""

    # Mandatory fields
    amount: float
    """Transaction amount (always positive, use transaction_type to determine debit/credit)."""
    currency: str = "EUR"
    """Currency code (e.g., 'EUR', 'USD', 'UAH')."""
    transaction_type: str
    """Either 'Credit' or 'Debit'."""
    details: str
    """Transaction description/details."""
    transaction_date: str
    """Transaction date in 'DD MMM YYYY' format."""

    # Optional fields
    balance: Optional[float] = None
    """Running balance after transaction (for debit accounts)."""
    reference: Optional[str] = None
    """Transaction reference number."""
    original_currency: Optional[str] = None
    """Original currency for foreign transactions."""
    original_amount: Optional[float] = None
    """Original amount in foreign currency."""
    exchange_rate: Optional[float] = None
    """Exchange rate used for conversion."""
    fx_fee: Optional[float] = None
    """Foreign exchange fee."""
    posting_date: Optional[str] = None
    """Posting date in 'DD MMM YYYY' format (for credit accounts)."""
