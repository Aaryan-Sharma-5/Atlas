"""Ingestion module: PDF, DOCX, GitHub, Markdown, and web parsers."""

from ingestion.chunker import TextChunk, chunk_text
from ingestion.github_parser import RepoContent, RepoDocument, ingest_repository
from ingestion.markdown_parser import MarkdownDoc, clean_markdown, parse_markdown
from ingestion.pdf_parser import PDFMetadata, extract_pdf_metadata

__all__ = [
    "extract_pdf_metadata",
    "PDFMetadata",
    "chunk_text",
    "TextChunk",
    "ingest_repository",
    "RepoContent",
    "RepoDocument",
    "parse_markdown",
    "clean_markdown",
    "MarkdownDoc",
]
