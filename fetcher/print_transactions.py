"""Print all transactions from a single PDF statement."""

import sys
from pathlib import Path

from parsers import parse_statement
from parsers.aib_debit import AIBDebitParser
from parsers.aib_credit import AIBCreditParser
from models import Transaction

# Import parsers to trigger registration
_ = AIBDebitParser()
_ = AIBCreditParser()


def main():
    if len(sys.argv) < 2:
        print("Usage: python print_transactions.py <pdf_file_path>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"ERROR: File not found: {pdf_path}")
        sys.exit(1)

    result = parse_statement(pdf_path)
    if not result:
        print(f"ERROR: Could not parse {pdf_path.name}")
        sys.exit(1)

    start_date, end_date, parser_name = result
    print(f"Parsing {pdf_path.name} ({parser_name})")
    print(f"Statement period: {start_date} to {end_date}\n")

    # Get parser instance and extract transactions
    if parser_name == "AIB Debit Account":
        parser = AIBDebitParser()
    elif parser_name == "AIB Credit Card":
        parser = AIBCreditParser()
    else:
        print(f"ERROR: Transaction extraction not implemented for {parser_name}")
        sys.exit(1)

    transactions = parser.extract_transactions(pdf_path)

    if not transactions:
        print("No transactions found.")
        return

    print(f"Extracted {len(transactions)} transactions\n")
    print("=" * 100)
    for i, tx in enumerate(transactions, 1):
        balance_str = (
            f"Balance: {tx.balance:,.2f}" if tx.balance is not None else "Balance: N/A"
        )
        print(
            f"{i:3d}. {tx.transaction_date}: {tx.amount:10.2f} {tx.currency} [{tx.transaction_type:6s}] | {balance_str:20s} | {tx.details}"
        )
    print("=" * 100)

    # Summary
    total_debit = sum(
        tx.amount for tx in transactions if tx.transaction_type == "Debit"
    )
    total_credit = sum(
        tx.amount for tx in transactions if tx.transaction_type == "Credit"
    )
    print(f"\nSummary:")
    print(f"  Debits: EUR {total_debit:,.2f}")
    print(f"  Credits: EUR {total_credit:,.2f}")
    print(f"  Net: EUR {total_credit - total_debit:,.2f}")


if __name__ == "__main__":
    main()
