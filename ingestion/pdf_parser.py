"""Extract text and metadata from PDF files."""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pdfplumber


@dataclass
class PDFMetadata:
    """Extracted PDF metadata and content."""
    file_path: str
    title: Optional[str]
    authors: list[str]
    page_count: int
    text: str
    file_hash: str
    language: str = "en"


def extract_pdf_metadata(pdf_path: str | Path) -> PDFMetadata:
    """Extract text and metadata from a PDF file.

    Args:
        pdf_path: Path to PDF file.

    Returns:
        PDFMetadata containing extracted text and metadata.

    Raises:
        FileNotFoundError: If PDF file does not exist.
        ValueError: If PDF cannot be read or is empty.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if not pdf_path.suffix.lower() == ".pdf":
        raise ValueError(f"File is not a PDF: {pdf_path}")

    # Compute file hash for deduplication
    file_hash = _compute_file_hash(pdf_path)

    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) == 0:
            raise ValueError(f"PDF is empty: {pdf_path}")

        page_count = len(pdf.pages)

        # Extract metadata from PDF info
        pdf_info = pdf.metadata or {}
        title = pdf_info.get("/Title") or pdf_info.get("Title")
        author = pdf_info.get("/Author") or pdf_info.get("Author")
        authors = [author] if author else []

        # Extract all text from all pages
        text = _extract_text_from_pdf(pdf)

    if not text or text.strip() == "":
        raise ValueError(f"No extractable text found in PDF: {pdf_path}")

    return PDFMetadata(
        file_path=str(pdf_path),
        title=title,
        authors=authors,
        page_count=page_count,
        text=text,
        file_hash=file_hash,
    )


def _extract_text_from_pdf(pdf: pdfplumber.PDF) -> str:
    """Extract text from all pages of a PDF.

    Args:
        pdf: Open pdfplumber PDF object.

    Returns:
        Concatenated text from all pages, with page markers.
    """
    pages_text = []
    for i, page in enumerate(pdf.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages_text.append(f"--- Page {i} ---\n{text}")

    return "\n\n".join(pages_text)


def _compute_file_hash(file_path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA256 hash of file for deduplication.

    Args:
        file_path: Path to file.
        chunk_size: Size of chunks to read (default 8KB).

    Returns:
        Hex SHA256 hash of file.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()
