"""Read a PDF and extract its bibliographic fields and page text."""

import re
from pathlib import Path
from typing import Optional

from pypdf import PdfReader
from pypdf.errors import PdfReadError


DOI_PATTERN = re.compile(r"(?<![\w.])10\.\d{4,9}/[-._;()/:a-z0-9]+", re.I | re.ASCII)
DOI_SEARCH_PAGES = 2


def clean_text(value: object) -> Optional[str]:
    """Treat missing, non-text and whitespace-only metadata as unknown."""
    if isinstance(value, str):
        return " ".join(value.split()) or None
    return None


def find_doi(text: str) -> Optional[str]:
    for match in DOI_PATTERN.finditer(text):
        # Remove trailing prose punctuation while preserving balanced DOI parentheses.
        candidate = match.group().rstrip(".;:")
        excess_closing = candidate.count(")") - candidate.count("(")
        while excess_closing > 0 and candidate.endswith(")"):
            candidate = candidate[:-1].rstrip(".;:")
            excess_closing -= 1
        if not candidate.endswith("/"):
            return candidate
    return None


def extract_pdf(path: Path, source: str, include_text: bool = False) -> dict:
    """Return one JSON-ready document record; raise if the PDF cannot be read."""
    with path.open("rb") as stream:
        reader = PdfReader(stream)
        if reader.is_encrypted:
            raise PdfReadError("PDF 已加密，请先使用文档阅读器解密。")

        metadata = reader.metadata or {}
        title = clean_text(metadata.get("/Title"))
        keywords = clean_text(metadata.get("/Keywords")) or ""
        metadata_doi = clean_text(metadata.get("/DOI")) or clean_text(metadata.get("/doi"))
        doi = find_doi(metadata_doi or "")
        page_count = len(reader.pages)
        pages_without_text = []
        pages = []

        for page_number, page in enumerate(reader.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            if not page_text:
                pages_without_text.append(page_number)
            if doi is None and page_number <= DOI_SEARCH_PAGES:
                doi = find_doi(page_text)
            if include_text:
                pages.append({"page_number": page_number, "text": page_text})

        record = {
            "source": source,
            "title": title or path.stem,
            "title_source": "metadata" if title else "filename",
            "author": clean_text(metadata.get("/Author")),
            "subject": clean_text(metadata.get("/Subject")),
            "keywords": [item.strip() for item in re.split(r"[,;，；]", keywords) if item.strip()],
            "doi": doi,
            "page_count": page_count,
            "pages_without_text": pages_without_text,
        }
        if include_text:
            record["pages"] = pages
        return record
