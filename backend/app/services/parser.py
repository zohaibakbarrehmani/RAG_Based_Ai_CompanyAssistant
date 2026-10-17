from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

import fitz  # PyMuPDF
from docx import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024


def _clean_text(value: str) -> str:
    if not value:
        return ""
    # Normalize whitespaces while preserving paragraph separation
    paragraphs = value.split("\n")
    cleaned_paragraphs = []
    for p in paragraphs:
        cleaned = " ".join(p.split())
        if cleaned:
            cleaned_paragraphs.append(cleaned)
    return "\n\n".join(cleaned_paragraphs)


def _detect_section(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:8]:
        if line.startswith("#"):
            return line.lstrip("#").strip() or "General"
        if len(line) < 90 and not line.endswith(".") and (":" in line or line.isupper() or line.istitle()):
            return line.rstrip(":")
    return "General"


def parse_pdf(file_path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    path_str = str(file_path)
    
    try:
        doc = fitz.open(path_str)
    except Exception as exc:
        raise ValueError(f"Unable to read PDF file: {exc}") from exc

    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            text = page.get_text("text").strip()
            
            # If standard text is sparse, try blocks
            if not text:
                blocks = page.get_text("blocks")
                block_texts = [b[4].strip() for b in blocks if len(b) > 4 and b[4].strip()]
                text = "\n".join(block_texts).strip()

            cleaned = _clean_text(text)
            section = _detect_section(cleaned) if cleaned else "General"
            records.append({
                "page": page_index + 1,
                "section": section,
                "text": cleaned,
            })
    finally:
        doc.close()

    # Filter out completely empty pages if there are other pages with content
    non_empty = [r for r in records if r["text"].strip()]
    if non_empty:
        return records
    return records or [{"page": 1, "section": "General", "text": ""}]


def parse_docx(file_path: str | Path) -> list[dict[str, Any]]:
    try:
        doc = DocxDocument(str(file_path))
    except (PackageNotFoundError, BadZipFile, Exception) as exc:
        raise ValueError(
            "This file is not a valid DOCX document or is corrupted. "
            "Please open it in Microsoft Word or Google Docs and re-save it as .docx."
        ) from exc

    records: list[dict[str, Any]] = []
    current_section = "General"
    current_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_lines
        if current_lines:
            text = _clean_text("\n".join(current_lines))
            if text:
                records.append({"page": 1, "section": current_section, "text": text})
            current_lines = []

    # Iterate through paragraphs
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        style = getattr(paragraph, "style", None)
        style_name = (getattr(style, "name", "") or "").lower()

        if style_name.startswith("heading") or style_name.startswith("title"):
            flush_current()
            current_section = text
            continue

        current_lines.append(text)

    # Also extract text from tables
    for table in doc.tables:
        for row in table.rows:
            row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_cells:
                # Remove duplicate adjacent cells from merged table cells
                deduped_cells: list[str] = []
                for cell_txt in row_cells:
                    if not deduped_cells or deduped_cells[-1] != cell_txt:
                        deduped_cells.append(cell_txt)
                current_lines.append(" | ".join(deduped_cells))

    flush_current()

    return records or [{"page": 1, "section": "General", "text": ""}]


def parse_text_file(file_path: str | Path) -> list[dict[str, Any]]:
    path = Path(file_path)
    content = ""
    # Try different encodings
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            content = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue

    if not content and path.stat().st_size > 0:
        content = path.read_bytes().decode("utf-8", errors="replace")

    lines = content.splitlines()
    current_section = "General"
    current_lines: list[str] = []
    records: list[dict[str, Any]] = []

    def flush_current() -> None:
        nonlocal current_lines
        if current_lines:
            text = _clean_text("\n".join(current_lines))
            if text:
                records.append({"page": 1, "section": current_section, "text": text})
            current_lines = []

    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            if current_lines:
                flush_current()
            continue

        heading_match = re.match(r"^(#{1,6}\s+.+|[A-Za-z0-9][A-Za-z0-9 /&-]{1,80}:)$", cleaned)
        if heading_match:
            flush_current()
            current_section = cleaned.lstrip("#").strip().rstrip(":") or current_section
            continue

        current_lines.append(cleaned)

    flush_current()
    return records or [{"page": 1, "section": "General", "text": _clean_text(content)}]


def parse_document(file_path: str | Path) -> list[dict[str, Any]]:
    path = Path(file_path)
    extension = path.suffix.lower()

    if extension == ".pdf":
        return parse_pdf(path)
    if extension == ".docx":
        return parse_docx(path)
    if extension in {".txt", ".md"}:
        return parse_text_file(path)

    raise ValueError(f"Unsupported file type: {extension}")
