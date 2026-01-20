"""Simple PDF reader for financial statements."""


def read_pdf(pdf_path: str) -> str:
    """Read text from a PDF file."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def main():
    print("Hello from Financial Statement Fetcher!")
    print("PDF libraries ready: pypdf, pdfplumber, pymupdf")
    print("SQLite: built-in with Python")


if __name__ == "__main__":
    main()
