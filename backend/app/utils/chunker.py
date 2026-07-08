"""Text chunking utilities — pure functions with no app dependencies.

Strategy:
- 1000-character chunks with 200-character overlap
- Respect sentence boundaries (no mid-sentence splits)
- Minimum chunk size: 100 characters (discard smaller)
- Section detection via heading-pattern matching
- Page tracking via ``[PAGE N]`` markers in parsed text
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Page markers
# ---------------------------------------------------------------------------

_PAGE_MARKER_RE = re.compile(r"\[PAGE\s+(\d+)\]")


def _find_page_markers(text: str) -> list[dict]:
    """Scan *text* for ``[PAGE N]`` markers.

    Returns a list of ``{"page_number": int, "char_position": int}`` dicts
    ordered by character position.  The markers are removed from *text*
    in-place via the returned positions.
    """
    markers: list[dict] = []
    for match in _PAGE_MARKER_RE.finditer(text):
        markers.append({
            "page_number": int(match.group(1)),
            "char_position": match.start(),
        })
    return markers


def _strip_page_markers(text: str) -> str:
    """Remove ``[PAGE N]`` markers from *text*."""
    return _PAGE_MARKER_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

_SECTION_PATTERNS = [
    # Markdown headings: ## Section Name  or  # Section Name
    re.compile(r"^#{1,2}\s+(.+)$", re.MULTILINE),
    # Bold-wrapped: **Section Name**
    re.compile(r"^\*\*(.+?)\*\*$", re.MULTILINE),
    # ALL-CAPS short lines (2-50 chars, only uppercase letters and spaces)
    re.compile(r"^([A-Z][A-Z\s]{1,49})$", re.MULTILINE),
    # Numbered sections: 1. Introduction, 2.3 Policies
    re.compile(r"^\d+(?:\.\d+)*\.?\s+(.+)$", re.MULTILINE),
]


def detect_sections(text: str) -> list[dict]:
    """Identify section boundaries in *text* using heading-pattern matching.

    Returns a list of ``{"title": str, "start_char": int, "end_char": int}``
    dicts ordered by character position.

    Also detects underline-style headings (text followed by ``===`` or
    ``---`` on the next line).
    """
    sections: list[dict] = []

    # --- regex-based patterns ---
    for pattern in _SECTION_PATTERNS:
        for match in pattern.finditer(text):
            sections.append({
                "title": match.group(1).strip(),
                "start_char": match.start(),
                "end_char": match.end(),
            })

    # --- underline-style headings ---
    underline_re = re.compile(r"^(.+)\n([=\-]{3,})\s*$", re.MULTILINE)
    for match in underline_re.finditer(text):
        sections.append({
            "title": match.group(1).strip(),
            "start_char": match.start(),
            "end_char": match.end(),
        })

    # Sort by position and return
    sections.sort(key=lambda s: s["start_char"])
    return sections


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_SENTENCE_END = re.compile(r"[.!?]\s+|\n\n")


def _find_sentence_boundary(text: str, target: int) -> int:
    """Find the nearest sentence boundary within ±50 chars of *target*.

    Searches forward first (up to 50 chars), then backward.
    Returns the position *after* the boundary punctuation, or *target*
    if no boundary is found.
    """
    window = 50
    # Search forward
    forward = min(target + window, len(text))
    for match in _SENTENCE_END.finditer(text, target, forward):
        return match.end()

    # Search backward
    backward = max(target - window, 0)
    last_boundary = target
    for match in _SENTENCE_END.finditer(text, backward, target):
        last_boundary = match.end()

    if last_boundary != target:
        return last_boundary

    return target


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    min_chunk_size: int = 100,
) -> list[dict]:
    """Split *text* into overlapping chunks of roughly *chunk_size* chars.

    Each chunk respects sentence boundaries where possible and includes the
    metadata needed for later section/page assignment.

    Returns a list of ``{"content": str, "chunk_index": int, "start_char":
    int, "end_char": int}`` dicts.  Chunks shorter than *min_chunk_size*
    are discarded and remaining chunks are re-indexed from 0.
    """
    if not text or not text.strip():
        return []

    cleaned = _strip_page_markers(text)
    cleaned_len = len(cleaned)

    chunks: list[dict] = []
    cursor = 0
    index = 0

    while cursor < cleaned_len:
        # Target end position for this chunk
        target_end = min(cursor + chunk_size, cleaned_len)

        if target_end >= cleaned_len:
            # Final chunk — take everything that's left
            split_point = cleaned_len
        else:
            split_point = _find_sentence_boundary(cleaned, target_end)

        chunk_content = cleaned[cursor:split_point].strip()

        if len(chunk_content) >= min_chunk_size:
            chunks.append({
                "content": chunk_content,
                "chunk_index": index,
                "start_char": cursor,
                "end_char": split_point,
            })
            index += 1

        # Advance cursor with overlap
        cursor = split_point - chunk_overlap
        if cursor <= chunks[-1]["start_char"] if chunks else 0:
            cursor = split_point  # prevent infinite loop on tiny text

    # Re-index after filtering
    for i, chunk in enumerate(chunks):
        chunk["chunk_index"] = i

    return chunks


# ---------------------------------------------------------------------------
# Section / page assignment
# ---------------------------------------------------------------------------


def assign_sections_to_chunks(
    chunks: list[dict],
    sections: list[dict],
) -> list[dict]:
    """Assign each chunk to the most recent section before its start position."""
    if not sections:
        return chunks

    for chunk in chunks:
        assigned: str | None = None
        for section in sections:
            if section["start_char"] <= chunk["start_char"]:
                assigned = section["title"]
            else:
                break
        chunk["section"] = assigned

    return chunks


def assign_page_to_chunks(
    chunks: list[dict],
    page_markers: list[dict],
) -> list[dict]:
    """Assign each chunk to the page whose marker precedes its start position."""
    if not page_markers:
        return chunks

    for chunk in chunks:
        assigned: int | None = None
        for marker in page_markers:
            if marker["char_position"] <= chunk["start_char"]:
                assigned = marker["page_number"]
            else:
                break
        chunk["page"] = assigned

    return chunks
