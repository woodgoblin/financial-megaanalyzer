"""Rename statement PDFs based on extracted dates and parser name."""

import argparse
import shutil
import sys
from pathlib import Path
from datetime import datetime

from analyze_aib_dates import analyze_statements, parse_date


def format_date_for_filename(date_str: str) -> str:
    """
    Format date string for use in filename.
    
    Converts "DD MMM YYYY" to "MMMYYYY" format (e.g., "19 Jan 2026" -> "Jan2026").
    
    Args:
        date_str: Date string in "DD MMM YYYY" format
        
    Returns:
        Formatted date string for filename
    """
    try:
        dt = parse_date(date_str)
        return f"{dt.strftime('%b')}{dt.year}"
    except (ValueError, AttributeError, TypeError):
        # Fallback: try to extract month and year manually
        parts = date_str.split()
        if len(parts) >= 3:
            try:
                month = parts[1][:3]  # First 3 chars of month
                year = int(parts[2])
                return f"{month}{year}"
            except (ValueError, IndexError):
                return "Unknown"
        return "Unknown"


def sanitize_parser_name(parser_name: str) -> str:
    """
    Sanitize parser name for use in filename.
    
    Replaces spaces and special characters with underscores.
    
    Args:
        parser_name: Parser name (e.g., "AIB Debit Account")
        
    Returns:
        Sanitized name (e.g., "AIB_Debit_Account")
    """
    return parser_name.replace(" ", "_").replace("-", "_")


def rename_statements(
    input_dir: Path,
    output_dir: Path = None,
    dry_run: bool = False
) -> dict:
    """
    Analyze statements and copy them with renamed filenames.
    
    Args:
        input_dir: Directory containing PDF statement files
        output_dir: Directory to copy renamed files to (default: input_dir / "renamed")
        dry_run: If True, only print what would be done without copying files
        
    Returns:
        Dictionary with statistics: {'copied': count, 'skipped': count, 'errors': count}
    """
    if output_dir is None:
        output_dir = input_dir / "renamed"
    
    # Run analysis
    analysis = analyze_statements(input_dir)
    if analysis is None:
        print(f"Error: Could not analyze directory {input_dir}", file=sys.stderr)
        return {'copied': 0, 'skipped': 0, 'errors': 1}
    
    # Create output directory
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    
    stats = {'copied': 0, 'skipped': 0, 'errors': 0}
    
    # Process each statement
    for stmt in analysis.statements:
        source_path = Path(stmt.file_path)
        
        # Skip files with errors or missing dates
        if stmt.error or not stmt.start_date or not stmt.end_date:
            print(f"Skipping {stmt.file_name}: {stmt.error or 'Missing dates'}")
            stats['skipped'] += 1
            continue
        
        # Skip files without parser name
        if not stmt.parser_name:
            print(f"Skipping {stmt.file_name}: No parser name")
            stats['skipped'] += 1
            continue
        
        # Generate new filename
        parser_sanitized = sanitize_parser_name(stmt.parser_name)
        start_formatted = format_date_for_filename(stmt.start_date)
        end_formatted = format_date_for_filename(stmt.end_date)
        
        # Preserve original extension
        extension = source_path.suffix
        new_filename = f"{parser_sanitized}_from_{start_formatted}_to_{end_formatted}{extension}"
        dest_path = output_dir / new_filename
        
        # Handle duplicate filenames
        if dest_path.exists() and not dry_run:
            counter = 1
            base_name = dest_path.stem
            while dest_path.exists():
                new_filename = f"{base_name}_{counter}{extension}"
                dest_path = output_dir / new_filename
                counter += 1
        
        if dry_run:
            print(f"Would copy: {stmt.file_name} -> {new_filename}")
        else:
            try:
                shutil.copy2(source_path, dest_path)
                print(f"Copied: {stmt.file_name} -> {new_filename}")
                stats['copied'] += 1
            except Exception as e:
                print(f"Error copying {stmt.file_name}: {e}", file=sys.stderr)
                stats['errors'] += 1
    
    return stats


def main():
    """Main entry point for the rename script."""
    parser = argparse.ArgumentParser(
        description="Rename statement PDFs based on extracted dates and parser name"
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing PDF statement files"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output directory for renamed files (default: input_dir/renamed)"
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Show what would be done without actually copying files"
    )
    
    args = parser.parse_args()
    
    # Validate input directory
    if not args.input_dir.exists():
        print(f"Error: Input directory does not exist: {args.input_dir}", file=sys.stderr)
        sys.exit(1)
    
    if not args.input_dir.is_dir():
        print(f"Error: Input path is not a directory: {args.input_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Run renaming
    stats = rename_statements(args.input_dir, args.output, args.dry_run)
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Files copied:  {stats['copied']}")
    print(f"Files skipped: {stats['skipped']}")
    print(f"Errors:        {stats['errors']}")
    
    if stats['errors'] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
