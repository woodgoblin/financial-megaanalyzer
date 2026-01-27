"""Script to extract and analyze transaction records from statements.

Supports:
- AIB Debit/Credit PDF statements
- Revolut Excel (.xlsx) exports
"""

import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

from parsers import parse_statement
from parsers.aib_debit import AIBDebitParser
from parsers.aib_credit import AIBCreditParser
from parsers.revolut_excel_transaction_extractor import RevolutExcelTransactionExtractor
from models import Transaction

# Import parsers to trigger registration
_ = AIBDebitParser()
_ = AIBCreditParser()


def parse_date(date_str: str) -> datetime:
    """Parse date string in 'DD MMM YYYY' format to datetime."""
    return datetime.strptime(date_str, "%d %b %Y")


def analyze_transactions_directory(
    statements_dir: Path,
    revolut_product: str = "Current",
) -> dict[str, list[Transaction]]:
    """
    Analyze transactions from all statements (PDF and Excel) in a directory.

    Args:
        statements_dir: Directory containing statement files
        revolut_product: Product filter for Revolut Excel files (default: "Current")

    Returns:
        Dictionary mapping file paths to lists of Transaction objects
    """
    results = {}

    # Process PDF files (AIB)
    pdf_files = sorted(statements_dir.glob("*.pdf"))
    for pdf_path in pdf_files:
        transactions = _extract_pdf_transactions(pdf_path)
        if transactions:
            results[str(pdf_path)] = transactions

    # Process Excel files (Revolut)
    excel_files = sorted(statements_dir.glob("*.xlsx"))
    for excel_path in excel_files:
        transactions = _extract_excel_transactions(excel_path, revolut_product)
        if transactions:
            results[str(excel_path)] = transactions

    return results


def _extract_pdf_transactions(pdf_path: Path) -> list[Transaction]:
    """Extract transactions from a PDF statement (AIB)."""
    result = parse_statement(pdf_path)
    if not result:
        print(f"WARNING: Could not parse {pdf_path.name}")
        return []

    start_date, end_date, parser_name = result

    # Get parser instance and extract transactions
    if parser_name == "AIB Debit Account":
        parser = AIBDebitParser()
        transactions = parser.extract_transactions(pdf_path)
    elif parser_name == "AIB Credit Card":
        parser = AIBCreditParser()
        transactions = parser.extract_transactions(pdf_path)
    else:
        print(f"WARNING: Transaction extraction not implemented for {parser_name}")
        return []

    if transactions:
        print(
            f"[OK] {pdf_path.name}: {len(transactions)} transactions ({start_date} to {end_date})"
        )

    return transactions


def _extract_excel_transactions(
    excel_path: Path, product: str = "Current"
) -> list[Transaction]:
    """Extract transactions from an Excel statement (Revolut)."""
    extractor = RevolutExcelTransactionExtractor(product=product)

    if not extractor.can_parse(excel_path):
        print(f"WARNING: Not a valid Revolut Excel file: {excel_path.name}")
        return []

    dates = extractor.extract_dates(excel_path)
    transactions = extractor.extract_transactions(excel_path)

    if transactions:
        date_range = f"{dates[0]} to {dates[1]}" if dates else "unknown dates"
        print(
            f"[OK] {excel_path.name}: {len(transactions)} transactions ({date_range}) [Product: {product}]"
        )

    return transactions


def analyze_debit_balances(transactions: list[Transaction]) -> dict | None:
    """
    Analyze balances for debit account transactions.

    Returns:
        Dictionary with balance analysis or None if not applicable
    """
    if not transactions:
        return None

    # Filter for debit account transactions (they have balance field)
    debit_txs = [tx for tx in transactions if tx.balance is not None]
    if not debit_txs:
        return None

    # Sort by date to find earliest and latest
    sorted_txs = sorted(debit_txs, key=lambda tx: parse_date(tx.transaction_date))

    # Skip OPENING BALANCE/BALANCE FORWARD entries when finding earliest transaction
    # They represent the starting balance, not a transaction that changes it
    earliest_tx = None
    for tx in sorted_txs:
        if (
            "BALANCE FORWARD" not in tx.details.upper()
            and "OPENING BALANCE" not in tx.details.upper()
        ):
            earliest_tx = tx
            break

    # If all transactions are OPENING BALANCE, use the first one
    if earliest_tx is None:
        earliest_tx = sorted_txs[0]

    latest_tx = sorted_txs[-1]

    # Starting balance (STATED): the balance shown in the statement for the earliest transaction date
    # This is the balance AFTER the first transaction
    stated_starting_balance = earliest_tx.balance

    # Starting balance (for calculation): the balance BEFORE the first transaction
    # If first transaction is a debit, balance before = balance after + amount
    # If first transaction is a credit, balance before = balance after - amount
    if earliest_tx.transaction_type == "Debit":
        calculated_starting_balance = earliest_tx.balance + earliest_tx.amount
    else:
        calculated_starting_balance = earliest_tx.balance - earliest_tx.amount

    # Ending balance: use the stated balance from the latest transaction with a balance
    # But also calculate it by processing all transactions to verify
    ending_balance = latest_tx.balance

    # Calculate total debits and credits (fees are handled separately in the running balance loop)
    # Exclude BALANCE FORWARD/OPENING BALANCE entries (they have amount 0.00 and are not real transactions)
    total_debits = sum(
        tx.amount
        for tx in transactions
        if tx.transaction_type == "Debit"
        and "BALANCE FORWARD" not in tx.details.upper()
        and "OPENING BALANCE" not in tx.details.upper()
    )
    total_credits = sum(
        tx.amount
        for tx in transactions
        if tx.transaction_type == "Credit"
        and "BALANCE FORWARD" not in tx.details.upper()
        and "OPENING BALANCE" not in tx.details.upper()
    )
    # Sum of fees (Revolut transactions may have separate fees)
    total_fees = sum(
        tx.fee or 0.0
        for tx in transactions
        if "BALANCE FORWARD" not in tx.details.upper()
        and "OPENING BALANCE" not in tx.details.upper()
    )

    # For debit accounts: starting balance decreases with debits, increases with credits
    calculated_ending = calculated_starting_balance - total_debits + total_credits

    # Also calculate ending balance by processing transactions in order (more accurate)
    # This handles cases where some transactions don't have explicit balances
    running_balance = calculated_starting_balance
    for tx in sorted(transactions, key=lambda tx: parse_date(tx.transaction_date)):
        if (
            "BALANCE FORWARD" in tx.details.upper()
            or "OPENING BALANCE" in tx.details.upper()
        ):
            continue  # Skip opening balance entries
        if tx.transaction_type == "Debit":
            running_balance -= tx.amount
        else:
            running_balance += tx.amount
        # Subtract fee if present (Revolut transactions)
        if tx.fee:
            running_balance -= tx.fee
        # If this transaction has a stated balance, use it to verify/correct running balance
        if tx.balance is not None:
            # Update running balance to match stated balance (in case of discrepancies)
            running_balance = tx.balance

    # Use the calculated running balance as the final calculated ending
    calculated_ending_from_running = running_balance
    discrepancy = calculated_ending_from_running - ending_balance

    return {
        "starting_balance": stated_starting_balance,  # Stated balance on earliest date
        "calculated_starting_balance": calculated_starting_balance,  # For calculation
        "ending_balance": ending_balance,
        "calculated_ending": calculated_ending_from_running,  # Use running balance calculation
        "discrepancy": discrepancy,
        "total_debits": total_debits,
        "total_credits": total_credits,
        "total_fees": total_fees,
        "earliest_date": earliest_tx.transaction_date,
        "latest_date": latest_tx.transaction_date,
    }


def print_transaction_summary(transactions_by_file: dict[str, list[Transaction]]):
    """Print summary statistics about transactions."""
    all_transactions = []
    for transactions in transactions_by_file.values():
        all_transactions.extend(transactions)

    if not all_transactions:
        print("\nNo transactions found.")
        return

    print(f"\n=== TRANSACTION SUMMARY ===")
    print(f"Total transactions: {len(all_transactions)}")
    print(f"Total files processed: {len(transactions_by_file)}")

    # Group by type
    by_type = defaultdict(int)
    by_currency = defaultdict(int)
    total_debit = 0.0
    total_credit = 0.0

    for tx in all_transactions:
        by_type[tx.transaction_type] += 1
        by_currency[tx.currency] += 1
        if tx.transaction_type == "Debit":
            total_debit += tx.amount
        else:
            total_credit += tx.amount

    print(f"\nBy type:")
    for tx_type, count in sorted(by_type.items()):
        print(f"  {tx_type}: {count}")

    print(f"\nBy currency:")
    for currency, count in sorted(by_currency.items()):
        print(f"  {currency}: {count}")

    # Sum of fees (Revolut transactions)
    total_fees = sum(tx.fee or 0.0 for tx in all_transactions)

    net_amount = total_credit - total_debit - total_fees

    print(f"\nTotal amounts:")
    print(f"  Debits: EUR{total_debit:,.2f}")
    print(f"  Credits: EUR{total_credit:,.2f}")
    if total_fees > 0:
        print(f"  Fees: EUR{total_fees:,.2f}")
    print(f"  Net: EUR{net_amount:,.2f}")

    # Balance analysis for debit accounts
    print(f"\n=== DEBIT ACCOUNT BALANCE ANALYSIS ===")
    debit_files = {}
    total_starting = 0.0
    total_ending = 0.0
    total_calculated = 0.0
    total_discrepancy = 0.0

    for file_path, transactions in transactions_by_file.items():
        balance_info = analyze_debit_balances(transactions)
        if balance_info:
            debit_files[file_path] = balance_info
            file_name = Path(file_path).name
            print(f"\n{file_name}:")
            print(
                f"  Period: {balance_info['earliest_date']} to {balance_info['latest_date']}"
            )
            print(
                f"  Starting balance (stated): EUR {balance_info['starting_balance']:,.2f}"
            )
            print(
                f"  Ending balance (stated): EUR {balance_info['ending_balance']:,.2f}"
            )
            print(
                f"  Calculated ending balance: EUR {balance_info['calculated_ending']:,.2f}"
            )
            print(
                f"  Ending balance discrepancy: EUR {balance_info['discrepancy']:,.2f}"
            )
            if balance_info["discrepancy"] != 0:
                print(f"    [WARNING] Discrepancy detected!")

    # Aggregate analysis: Collect ALL transactions, deduplicate, sort by date, and analyze
    if debit_files:
        # Collect all transactions from all debit files
        all_debit_transactions = []
        for file_path, transactions in transactions_by_file.items():
            balance_info = analyze_debit_balances(transactions)
            if balance_info:  # Only include files with balance info (debit accounts)
                all_debit_transactions.extend(transactions)

        if all_debit_transactions:
            # Deduplicate transactions (files may overlap, causing same transaction to appear multiple times)
            # Use a signature: date, amount, type, and details (first 100 chars) to identify duplicates
            seen_signatures = set()
            unique_transactions = []
            for tx in all_debit_transactions:
                # Create signature for deduplication
                sig = (
                    tx.transaction_date,
                    tx.amount,
                    tx.transaction_type,
                    tx.details[:100],
                )
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    unique_transactions.append(tx)

            duplicates_removed = len(all_debit_transactions) - len(unique_transactions)

            # Sort all unique transactions chronologically by date
            sorted_all_txs = sorted(
                unique_transactions, key=lambda tx: parse_date(tx.transaction_date)
            )

            # Analyze the sorted transactions
            aggregate_info = analyze_debit_balances(sorted_all_txs)

            if aggregate_info:
                print(
                    f"\n=== AGGREGATE BALANCE ANALYSIS (All Transactions Sorted by Date) ==="
                )
                print(f"  Total transactions collected: {len(all_debit_transactions)}")
                if duplicates_removed > 0:
                    print(
                        f"  Duplicates removed: {duplicates_removed} (from overlapping files)"
                    )
                print(f"  Unique transactions analyzed: {len(sorted_all_txs)}")
                print(
                    f"  Period: {aggregate_info['earliest_date']} to {aggregate_info['latest_date']}"
                )
                print(
                    f"  Starting balance (stated): EUR {aggregate_info['starting_balance']:,.2f}"
                )
                print(
                    f"  Ending balance (stated): EUR {aggregate_info['ending_balance']:,.2f}"
                )
                print(f"  Total debits: EUR {aggregate_info['total_debits']:,.2f}")
                print(f"  Total credits: EUR {aggregate_info['total_credits']:,.2f}")
                if aggregate_info.get("total_fees", 0) > 0:
                    print(f"  Total fees: EUR {aggregate_info['total_fees']:,.2f}")
                print(
                    f"  Calculated ending balance: EUR {aggregate_info['calculated_ending']:,.2f}"
                )
                print(
                    f"  Ending balance discrepancy: EUR {aggregate_info['discrepancy']:,.2f}"
                )
                if aggregate_info["discrepancy"] != 0:
                    print(f"    [WARNING] Aggregate discrepancy detected!")

    # Foreign currency transactions
    fx_transactions = [tx for tx in all_transactions if tx.original_currency]
    if fx_transactions:
        print(f"\nForeign currency transactions: {len(fx_transactions)}")
        for tx in fx_transactions[:5]:
            print(
                f"  {tx.transaction_date}: {tx.original_amount} {tx.original_currency} @ {tx.exchange_rate} = €{tx.amount}"
            )


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_transactions.py <statements_directory> [product]")
        print("\nArguments:")
        print("  statements_directory  Directory containing statement files")
        print("  product               Revolut product filter (default: Current)")
        print("                        Options: Current, Savings, Deposit")
        print("\nExamples:")
        print("  python analyze_transactions.py ../statements_raw/aib/debit")
        print("  python analyze_transactions.py ../statements_raw/aib/credit")
        print("  python analyze_transactions.py ../statements_raw/revolut")
        print("  python analyze_transactions.py ../statements_raw/revolut Savings")
        sys.exit(1)

    statements_dir = Path(sys.argv[1])
    if not statements_dir.exists():
        print(f"ERROR: Directory not found: {statements_dir}")
        sys.exit(1)

    # Optional product filter for Revolut
    product = sys.argv[2] if len(sys.argv) > 2 else "Current"

    print(f"Analyzing transactions from: {statements_dir}")
    if any(statements_dir.glob("*.xlsx")):
        print(f"Revolut product filter: {product}")
    print()

    transactions_by_file = analyze_transactions_directory(
        statements_dir, revolut_product=product
    )
    print_transaction_summary(transactions_by_file)


if __name__ == "__main__":
    main()
