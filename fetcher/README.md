# Fetcher

[![Tests](https://github.com/woodgoblin/financial-megaanalyzer/actions/workflows/ci.yml/badge.svg?label=tests)](https://github.com/woodgoblin/financial-megaanalyzer/actions/workflows/ci.yml)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Minimal skeleton for financial statement PDF processing.

## Setup

```bash
cd fetcher
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Test

```bash
pytest
```

## Usage: Statement Analysis

To analyze statements:
```bash
python analyze_aib_dates.py ../statements_raw/aib/debit
python analyze_aib_dates.py ../statements_raw/aib/credit
python analyze_aib_dates.py ../statements_raw/revolut/debit-eur
```

## Usage: Statement File Renaming

Rename statement PDFs with descriptive filenames for better document keeping, file indexing, and submitting applications requiring statements dating back multiple years.

The renamer copies files to a `renamed` folder with format: `<ParserName>_from_<MMMYYYY>_to_<MMMYYYY>.pdf`

```bash
# Rename files (creates input_dir/renamed folder)
python rename_statements.py ../statements_raw/aib/debit

# Custom output directory
python rename_statements.py ../statements_raw/aib/debit -o /path/to/output

# Dry run (preview without copying)
python rename_statements.py ../statements_raw/aib/debit -n
```

## Known Issues

### Duplicate Detection Limitations

Duplicate detection is based on **binary file content** (SHA256 hash), not content analysis. This means:

- ✅ **Works**: Identical PDF files (byte-for-byte) are correctly flagged as duplicates
- ❌ **Limitation**: Same statements generated at different times may have different binary content (due to PDF metadata, timestamps, internal structure) and will **not** be detected as duplicates, even if they represent the same statement period
