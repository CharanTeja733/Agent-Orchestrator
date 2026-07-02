"""Document parsing utilities — pure functions with no app dependencies."""

import io
import re
from pathlib import Path

from PyPDF2 import PdfReader
from docx import Document as DocxDocument

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_file_type(filename: str) -> bool:
    """Check whether the file extension is allowed."""
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def parse_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF, inserting ``[PAGE N]`` markers after each page.

    Raises ``ValueError`` if the file cannot be read as a PDF.
    """
    stream = io.BytesIO(file_bytes)
    try:
        reader = PdfReader(stream)
    except Exception as exc:
        raise ValueError(f"Failed to read PDF: {exc}") from exc

    pages: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        if text:
            pages.append(text.strip())
            pages.append(f"[PAGE {i}]")

    return "\n\n".join(pages).strip()


def parse_docx(file_bytes: bytes) -> str:
    """Extract text from a DOCX file.

    Paragraphs whose style starts with ``"Heading"`` are prefixed with
    ``## `` to aid section detection later in the chunker.
    """
    stream = io.BytesIO(file_bytes)
    try:
        doc = DocxDocument(stream)
    except Exception as exc:
        raise ValueError(f"Failed to read DOCX: {exc}") from exc

    paragraphs: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            paragraphs.append("")
            continue

        style_name = para.style.name if para.style else ""
        if style_name.lower().startswith("heading"):
            paragraphs.append(f"## {text}")
        else:
            paragraphs.append(text)

    return "\n\n".join(paragraphs).strip()


def parse_txt(file_bytes: bytes) -> str:
    """Decode a plain-text file, falling back through common encodings."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return file_bytes.decode(encoding).strip()
        except UnicodeDecodeError:
            continue

    # Last resort
    return file_bytes.decode("utf-8", errors="replace").strip()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Route *file_bytes* to the correct parser based on *filename* extension.

    Raises ``ValueError`` for unsupported file types or empty output.
    """
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        text = parse_pdf(file_bytes)
    elif ext == ".docx":
        text = parse_docx(file_bytes)
    elif ext == ".txt":
        text = parse_txt(file_bytes)
    else:
        raise ValueError(
            f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if not text.strip():
        raise ValueError("No extractable text found in the document")

    return text
