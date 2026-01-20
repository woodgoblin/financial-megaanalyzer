# financial-megaanalyzer
My attempt to have a tool that extracts info from bank statements (omitting bothersome integrations) and then running visualizations/data analysis on it.

## Usage

### Analyze AIB Statements

```bash
cd fetcher

# Analyze debit statements with default dir structure (default)
python analyze_aib_dates.py

# Analyze any directory with credit/debit PDFs
python analyze_aib_dates.py /path/to/statements
```

### Setup

```bash
cd fetcher
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate      # Linux/Mac
pip install -r requirements.txt
```

### Run Tests

```bash
cd fetcher
pytest
```