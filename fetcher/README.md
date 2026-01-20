# Fetcher

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

## Libraries

- **pypdf** (6.6.0+) - PDF reading
- **pdfplumber** (0.11.4+) - PDF table extraction
- **pymupdf** (1.24.14+) - PDF analysis
- **sqlite3** - Built-in with Python

## Known Issues

### Duplicate Detection Limitations

Duplicate detection is based on **binary file content** (SHA256 hash), not content analysis. This means:

- ✅ **Works**: Identical PDF files (byte-for-byte) are correctly flagged as duplicates
- ❌ **Limitation**: Same statements generated at different times may have different binary content (due to PDF metadata, timestamps, internal structure) and will **not** be detected as duplicates, even if they represent the same statement period
