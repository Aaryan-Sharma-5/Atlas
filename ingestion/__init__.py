"""Ingestion module: PDF, DOCX, GitHub, Markdown, and web parsers."""

from ingestion.chunker import TextChunk, chunk_text
from ingestion.pdf_parser import PDFMetadata, extract_pdf_metadata

__all__ = [
    "extract_pdf_metadata",
    "PDFMetadata",
    "chunk_text",
    "TextChunk",
]
