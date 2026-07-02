"""Chunk text into fixed-size segments for processing."""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class TextChunk:
    """A segment of text with metadata."""
    content: str
    chunk_index: int
    source_file: str
    page_markers: list[int]


def chunk_text(
    text: str,
    source_file: str,
    target_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[TextChunk]:
    """Chunk text into fixed-size segments.

    Uses a simple token counter (whitespace-based). Each "token" is roughly
    a word or punctuation element. This is a placeholder strategy; will be
    revisited for better semantic chunking in Phase 2.

    Args:
        text: Full text to chunk.
        source_file: Source file identifier (for tracking).
        target_tokens: Target tokens per chunk (default 500).
        overlap_tokens: Tokens to overlap between chunks (default 50).

    Returns:
        List of TextChunk objects.

    Raises:
        ValueError: If text is empty or target_tokens <= 0.
    """
    if not text or text.strip() == "":
        raise ValueError("Text cannot be empty")
    if target_tokens <= 0:
        raise ValueError("target_tokens must be positive")

    # Tokenize text, keeping each token's character span so chunk boundaries can be located exactly (no substring search needed).
    tokens = _tokenize_with_positions(text)

    if len(tokens) == 0:
        raise ValueError("No tokens extracted from text")

    # Extract page markers from text (e.g., "--- Page 1 ---")
    page_markers = _extract_page_markers(text)

    chunks = []
    chunk_index = 0
    start_idx = 0

    while start_idx < len(tokens):
        # Calculate end index for this chunk
        end_idx = min(start_idx + target_tokens, len(tokens))

        # Extract tokens for this chunk
        chunk_tokens = tokens[start_idx:end_idx]
        chunk_text = " ".join(tok for tok, _, _ in chunk_tokens)

        # Locate this chunk by its actual character span, not by re-searching for its text (which breaks on repeated content).
        chunk_start_char = chunk_tokens[0][1]
        chunk_end_char = chunk_tokens[-1][2]
        chunk_pages = _find_pages_in_span(
            chunk_start_char, chunk_end_char, page_markers
        )

        chunks.append(
            TextChunk(
                content=chunk_text,
                chunk_index=chunk_index,
                source_file=source_file,
                page_markers=chunk_pages,
            )
        )

        chunk_index += 1

        # Move start index with overlap
        start_idx = end_idx - overlap_tokens
        if start_idx < 0:
            start_idx = 0

        # Avoid infinite loop at end of text
        if end_idx == len(tokens):
            break

    return chunks


def _tokenize_with_positions(text: str) -> list[tuple[str, int, int]]:
    """Simple tokenization: split on whitespace, tracking character spans.

    Args:
        text: Text to tokenize.

    Returns:
        List of (token, start_char, end_char) tuples.
    """
    return [(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def _extract_page_markers(text: str) -> dict[int, int]:
    """Extract page numbers and their positions in text.

    Looks for patterns like "--- Page N ---".

    Args:
        text: Full text with page markers.

    Returns:
        Dict mapping page number to character position in text.
    """
    page_markers = {}
    lines = text.split("\n")
    char_pos = 0

    for line in lines:
        if line.strip().startswith("--- Page") and line.strip().endswith("---"):
            # Extract page number (e.g., "--- Page 5 ---" -> 5)
            try:
                parts = line.strip().split()
                page_num = int(parts[2])
                page_markers[page_num] = char_pos
            except (IndexError, ValueError):
                pass

        char_pos += len(line) + 1  # +1 for newline

    return page_markers


def _find_pages_in_span(
    chunk_start: int,
    chunk_end: int,
    page_markers: dict[int, int],
) -> list[int]:
    """Find which pages a character span falls within.

    Args:
        chunk_start: Start character position of the chunk in the source text.
        chunk_end: End character position of the chunk in the source text.
        page_markers: Dict mapping page number to position.

    Returns:
        List of page numbers this chunk spans.
    """
    pages = []
    for page_num in sorted(page_markers.keys()):
        page_start = page_markers[page_num]
        next_page_start = page_markers.get(page_num + 1, chunk_end + 1)

        # Check if chunk overlaps with this page
        if chunk_start < next_page_start and chunk_end > page_start:
            pages.append(page_num)

    return pages if pages else [1]  # Default to page 1 if no markers found
