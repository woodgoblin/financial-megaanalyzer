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
