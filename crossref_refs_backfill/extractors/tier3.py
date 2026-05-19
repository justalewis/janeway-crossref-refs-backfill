"""
Tier 3 extractor: PDF + GROBID.

Ported from Poroi/scripts/02c_extract_tier3.py with a content-based
primary that accepts PDF bytes directly (so the Janeway plugin can
pass `galley.file.get_file(article)` without writing to disk first).

Connects to GROBID via HTTP. The plugin's `providers.py` raises
GROBIDUnreachable when the sidecar isn't running so deposit attempts
on PDF-only journals don't crash — they just defer.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests


DEFAULT_GROBID_URL = "http://localhost:8070"
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


_MLA_HEADER_PATTERN = re.compile(
    r"\b(?:WORKS\s+CITED|Works\s+Cited|REFERENCES\s+CITED|"
    r"References\s+Cited|NOTES\s+AND\s+REFERENCES|Notes\s+and\s+References)\b",
    re.IGNORECASE,
)
_YEAR_PAREN = re.compile(r"\(\d{4}[a-z]?\)")


class GROBIDUnreachable(Exception):
    """GROBID sidecar isn't responding. Caller should treat as 'skip Tier 3'."""


def _clean(text: str) -> str:
    return " ".join(text.split())


def _looks_like_reference(text: str) -> bool:
    if not text or len(text) < 40:
        return False
    has_year = bool(re.search(r"(18|19|20)\d{2}", text))
    has_structure = text.count(",") >= 3
    return has_year or has_structure


def _likely_merged(text: str) -> bool:
    return len(_YEAR_PAREN.findall(text)) >= 2


def _reconstruct(bibl: ET.Element) -> str:
    parts = []
    for elem in bibl.iter():
        if elem.text and elem.text.strip():
            parts.append(elem.text.strip())
    return _clean(" ".join(parts))


def parse_tei(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    doi_elem = root.find(".//tei:teiHeader//tei:idno[@type='DOI']", TEI_NS)
    doi = doi_elem.text.strip() if doi_elem is not None and doi_elem.text else None
    references: list[str] = []
    dropped: list[str] = []
    for bibl in root.findall(".//tei:listBibl/tei:biblStruct", TEI_NS):
        raw = bibl.find("tei:note[@type='raw_reference']", TEI_NS)
        text = _clean(raw.text) if raw is not None and raw.text else _reconstruct(bibl)
        if not _looks_like_reference(text):
            if text:
                dropped.append(text)
            continue
        references.append(text)
    return {"doi": doi, "references": references, "dropped": dropped}


def _extract_mla_references(tei_xml: str) -> list[str]:
    """Fallback for older humanities papers GROBID's section-header
    detector misses ("WORKS CITED" instead of "References")."""
    m = _MLA_HEADER_PATTERN.search(tei_xml)
    if not m:
        return []
    start = m.end()
    end_candidates = [
        tei_xml.find(tag, start) for tag in ("</body>", "<back", "<figure")
    ]
    end_candidates = [i for i in end_candidates if i > start]
    end = min(end_candidates) if end_candidates else len(tei_xml)
    section = tei_xml[start:end]

    first_chunk = section.split("</p>", 1)[0]
    candidates: list[str] = []
    leading = re.sub(r"<[^>]+>", "", first_chunk).strip()
    if leading:
        candidates.append(_clean(leading))
    for match in re.finditer(r"<p[^>]*>(.*?)</p>", section, flags=re.DOTALL):
        text = re.sub(r"<[^>]+>", "", match.group(1))
        text = _clean(text)
        if text and text not in candidates:
            candidates.append(text)

    references = []
    for text in candidates:
        if not _looks_like_reference(text):
            continue
        references.append(text)
    return references


def extract_from_pdf_bytes(
    pdf_bytes: bytes,
    *,
    pdf_filename: str = "article.pdf",
    grobid_url: str = DEFAULT_GROBID_URL,
) -> dict:
    """Primary plugin entry point. POSTs PDF bytes to GROBID and parses TEI.

    Raises GROBIDUnreachable on connection errors so the deposit
    pipeline can silently defer to the next provider instead of
    crashing.
    """
    endpoint = f"{grobid_url}/api/processFulltextDocument"
    try:
        response = requests.post(
            endpoint,
            files={"input": (pdf_filename, io.BytesIO(pdf_bytes), "application/pdf")},
            data={
                "includeRawCitations": "1",
                "consolidateHeader": "1",
                "consolidateCitations": "0",
            },
            timeout=600,
        )
    except (requests.ConnectionError, requests.Timeout) as e:
        raise GROBIDUnreachable(str(e)) from e

    response.raise_for_status()
    result = parse_tei(response.text)
    if not result["references"]:
        mla_refs = _extract_mla_references(response.text)
        if mla_refs:
            result["references"] = mla_refs
            result["mla_fallback_used"] = True
    result.setdefault("mla_fallback_used", False)
    result["tier"] = "tier3"
    return result


def extract(path: Path, *, grobid_url: str = DEFAULT_GROBID_URL) -> dict:
    """Path-based wrapper for local sandbox testing."""
    pdf_bytes = Path(path).read_bytes()
    result = extract_from_pdf_bytes(
        pdf_bytes,
        pdf_filename=Path(path).name,
        grobid_url=grobid_url,
    )
    result["source"] = str(path)
    return result
