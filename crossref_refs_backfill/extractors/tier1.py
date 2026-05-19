"""
Tier 1 extractor: structured-HTML reference parsing.

Ported from Poroi/scripts/02_extract_tier1.py with one change: the
primary entry point takes the HTML string directly (so the Janeway
plugin can pass `galley.file.get_file(article)` without writing to
disk). A `extract(path)` wrapper is kept for local sandbox testing.

Targets bepress-era HTML galleys whose references appear as
<p class="ref"> paragraphs inside a "References" or "List of References"
section. Output is plain-text citation strings, ready to wrap as
<unstructured_citation> in CrossRef deposit XML.

Handles:
  - Section heading variation ("References" vs "List of References")
  - Em-dash author repeats: "———. 1941. ..." substitutes for the
    previous entry's authors
  - Inline <i>, <b>, <a> tags flattened to plain text
  - Whitespace stranded by adjacent inline tags (e.g. "title ." -> "title.")
  - Article DOI from <p class="doi"> when present
"""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup


_EMDASH_REPEAT_RE = re.compile(r"^[—–\-]{2,}\s*[.,]\s*")
_YEAR_RE = re.compile(r"\(?(?:18|19|20)\d{2}[a-z]?\)?[.,]")
_DOI_RE = re.compile(r"10\.\d{4,9}/\S+")
_PRE_PUNCT_SPACE_RE = re.compile(r"\s+([.,;:?!])")


def _clean(text: str) -> str:
    text = " ".join(text.split())
    return _PRE_PUNCT_SPACE_RE.sub(r"\1", text)


def _split_authors_year(ref: str) -> tuple[str, str]:
    m = _YEAR_RE.search(ref)
    if not m:
        return ref, ""
    return ref[: m.start()].rstrip(" .,"), ref[m.start():]


def _expand_emdash(ref: str, prev_authors: str) -> str:
    if not prev_authors:
        return ref
    return _EMDASH_REPEAT_RE.sub(prev_authors + ". ", ref, count=1)


def extract_doi(soup: BeautifulSoup) -> str | None:
    p = soup.find("p", class_="doi")
    if p is None:
        return None
    text = p.get_text(" ", strip=True)
    m = _DOI_RE.search(text)
    return m.group(0).rstrip(".,;") if m else None


def extract_references(html: str) -> list[str]:
    """Return the list of plain-text reference strings from a Tier 1 HTML."""
    soup = BeautifulSoup(html, "lxml")
    ref_paragraphs = soup.find_all("p", class_="ref")
    references: list[str] = []
    prev_authors = ""
    for p in ref_paragraphs:
        text = _clean(p.get_text(" "))
        if not text:
            continue
        text = _expand_emdash(text, prev_authors)
        references.append(text)
        authors, _ = _split_authors_year(text)
        if authors:
            prev_authors = authors
    return references


def extract_from_html(html: str) -> dict:
    """Primary plugin entry point. Returns {doi, references, tier}."""
    soup = BeautifulSoup(html, "lxml")
    return {
        "doi": extract_doi(soup),
        "references": extract_references(html),
        "tier": "tier1",
    }


def extract(path: Path) -> dict:
    """Path-based wrapper for local sandbox testing."""
    html = Path(path).read_text(encoding="utf-8", errors="replace")
    result = extract_from_html(html)
    result["source"] = str(path)
    return result
