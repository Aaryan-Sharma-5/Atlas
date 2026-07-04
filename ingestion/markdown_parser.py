"""Markdown cleanup for NER. Strips syntax that pollutes entity spans
(code fences, link URLs, emphasis markers); deliberately not a full
CommonMark parser — NER needs clean prose, not a DOM.
"""

import re
from dataclasses import dataclass
from pathlib import Path

_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HTML_TAG = re.compile(r"<[^>\n]+>")
_HEADING_MARK = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_EMPHASIS = re.compile(r"(\*{1,3}|_{1,3})(\S(?:.*?\S)?)\1")


@dataclass
class MarkdownDoc:
    file_path: str
    title: str | None
    text: str


def parse_markdown(path: str | Path) -> MarkdownDoc:
    path = Path(path)
    raw = path.read_text(encoding="utf-8", errors="replace")

    heading = re.search(r"^#{1,6}\s+(.+)$", raw, re.MULTILINE)
    title = heading.group(1).strip() if heading else None

    return MarkdownDoc(file_path=str(path), title=title, text=clean_markdown(raw))


def clean_markdown(raw: str) -> str:
    """Markdown -> plain prose. Order matters: fences before inline code,
    images before links (image syntax contains link syntax)."""
    text = _CODE_FENCE.sub(" ", raw)
    text = _INLINE_CODE.sub(" ", text)
    text = _IMAGE.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = _HTML_TAG.sub(" ", text)
    text = _HEADING_MARK.sub("", text)
    text = _EMPHASIS.sub(r"\2", text)
    return text
