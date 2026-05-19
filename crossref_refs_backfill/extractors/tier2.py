"""
Tier 2 extractor: footnoted Chicago notes-bibliography.

Ported from Poroi/scripts/02b_extract_tier2.py. Same content-based
primary as Tier 1.

Targets early-bepress HTML galleys (~2003 era) with table-based
numbered paragraphs and references embedded in <p class="endnotes">
footnotes. The footnote section mixes four content types:

  1. Full citations         — emitted to output
  2. Short-form references  — refer back to a prior full citation; skipped
  3. Ibid. references       — refer to previous footnote; skipped
  4. Discursive notes       — pure commentary; skipped

The classifier is heuristic, not LLM-based. v1 ships without LLM
dependency; an LLM-assist pass per "full" footnote is the planned
future tightening. Marked `requires_review = True` in
ParsedReferenceList because false positives slip through.
"""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup


_DOI_RE = re.compile(r"10\.\d{4,9}/\S+")
_PRE_PUNCT_SPACE_RE = re.compile(r"\s+([.,;:?!])")
_LEADING_NUMBER_RE = re.compile(r"^\d+\s+")
_YEAR_RE = re.compile(r"\b(?:18|19|20)\d{2}\b")
_PAGE_REF_RE = re.compile(r"\bpp?\.\s*\d", re.IGNORECASE)
_SENTENCE_BREAK_RE = re.compile(r"\.\s+[A-Z]")
_IBID_RE = re.compile(r"^\s*ibid\b", re.IGNORECASE)
_FIRST_PERSON_RE = re.compile(r"^(?:I|We|My|Our)\b")


def _clean(text: str) -> str:
    text = " ".join(text.split())
    return _PRE_PUNCT_SPACE_RE.sub(r"\1", text)


def _strip_footnote_number(text: str) -> str:
    return _LEADING_NUMBER_RE.sub("", text, count=1)


def _classify(text: str) -> str:
    """Return 'ibid', 'short_form', 'discursive', or 'full'."""
    if _IBID_RE.match(text):
        return "ibid"
    if _FIRST_PERSON_RE.match(text):
        return "discursive"

    has_year = bool(_YEAR_RE.search(text))
    sentence_breaks = len(_SENTENCE_BREAK_RE.findall(text))
    has_page = bool(_PAGE_REF_RE.search(text))

    if sentence_breaks >= 3 and not has_year:
        return "discursive"
    if not has_year and len(text) < 100:
        return "short_form"
    if not has_year and len(text) > 80 and not has_page:
        return "discursive"
    return "full"


def extract_doi(soup: BeautifulSoup) -> str | None:
    p = soup.find("p", class_="doi")
    if p is None:
        return None
    text = p.get_text(" ", strip=True)
    m = _DOI_RE.search(text)
    return m.group(0).rstrip(".,;") if m else None


def extract_references(html: str) -> tuple[list[str], dict[str, int]]:
    """Return (full_citations, classification_counts)."""
    soup = BeautifulSoup(html, "lxml")
    endnotes = soup.find_all("p", class_="endnotes")
    counts = {"full": 0, "short_form": 0, "ibid": 0, "discursive": 0, "empty": 0}
    full_citations: list[str] = []
    for p in endnotes:
        text = _clean(p.get_text(" "))
        text = _strip_footnote_number(text)
        if not text:
            counts["empty"] += 1
            continue
        kind = _classify(text)
        counts[kind] += 1
        if kind == "full":
            full_citations.append(text)
    return full_citations, counts


def extract_from_html(html: str) -> dict:
    """Primary plugin entry point."""
    soup = BeautifulSoup(html, "lxml")
    refs, counts = extract_references(html)
    return {
        "doi": extract_doi(soup),
        "references": refs,
        "tier": "tier2",
        "classification_counts": counts,
    }


def extract(path: Path) -> dict:
    """Path-based wrapper for local sandbox testing."""
    html = Path(path).read_text(encoding="utf-8", errors="replace")
    result = extract_from_html(html)
    result["source"] = str(path)
    return result
