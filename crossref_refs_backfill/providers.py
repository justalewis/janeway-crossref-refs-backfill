"""
Citation-list providers registered with Janeway's Crossref deposit
pipeline. Three providers in priority order:

  1. from_stored_reference_list — cached XML from a prior extraction
  2. from_html_galley           — parse on-demand from a Tier 1/2 HTML galley
  3. from_pdf_galley            — GROBID-parse a PDF galley

Each provider takes a `submission.Article` instance and returns either
a string containing `<citation_list>...</citation_list>` XML, or `None`
to defer to the next provider. The deposit pipeline (per the proposal
in INTEGRATION-SKETCH.md) walks providers in registration order and
uses the first non-None result.

Empirical match-rate baseline from a 5-article Poroi sample (May 2026):
Tier 1 HTML ~31–38%, Tier 2 HTML ~22%, Tier 3 PDF ~17–56% (Janeway-era
content is at the high end). See ../Poroi/CALL-PREP.md.
"""

from __future__ import annotations

import os

from crossref_refs_backfill.extractors import detect, tier1, tier2, tier3, build_xml
from crossref_refs_backfill.models import ParsedReferenceList


# GROBID endpoint. Tier 3 is skipped if this isn't reachable, so the
# plugin still functions for journals that have only Tier 1/2 content.
GROBID_URL = os.environ.get("GROBID_URL", "http://localhost:8070")


def from_stored_reference_list(article) -> str | None:
    """Highest-priority provider. Returns the cached citation_list XML
    from a prior extraction, or None if this article hasn't been
    extracted yet.

    Backfill runs populate this cache eagerly via the
    `backfill_references` management command; subsequent deposits read
    from cache instead of re-parsing.
    """
    try:
        return article.parsed_reference_list.citation_list_xml
    except ParsedReferenceList.DoesNotExist:
        return None


def from_html_galley(article) -> str | None:
    """Tier 1/2: parse references directly from an HTML galley if one
    exists. Caches the result so subsequent deposits don't re-parse.

    Picks the article's first HTML galley by sequence. Detects tier 1
    (structured `<p class='ref'>`) vs tier 2 (footnoted endnotes)
    using content markers; falls through to the next provider if
    neither shape is recognized.
    """
    html_galley = (
        article.galley_set.filter(file__mime_type="text/html")
        .order_by("sequence")
        .first()
    )
    if not html_galley:
        return None

    html = html_galley.file.get_file(article)
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")

    tier = detect.detect_tier_from_html(html)
    if tier == "tier1":
        result = tier1.extract_from_html(html)
    elif tier == "tier2":
        result = tier2.extract_from_html(html)
    else:
        return None

    if not result.get("references"):
        return None

    citation_list_xml = build_xml.to_citation_list_xml(result, include_comment=False)
    _cache(article, citation_list_xml, tier, len(result["references"]))
    return citation_list_xml


def from_pdf_galley(article) -> str | None:
    """Tier 3: POST a PDF galley to GROBID, parse the TEI, cache the
    result. Skipped silently if GROBID is unreachable so the plugin
    doesn't crash deposit attempts for journals that haven't deployed
    a GROBID sidecar.
    """
    pdf_galley = article.pdfs.order_by("sequence").first()
    if not pdf_galley:
        return None

    pdf_bytes = pdf_galley.file.get_file(article)
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode("utf-8")

    try:
        result = tier3.extract_from_pdf_bytes(
            pdf_bytes,
            pdf_filename=getattr(pdf_galley.file, "original_filename", "article.pdf"),
            grobid_url=GROBID_URL,
        )
    except tier3.GROBIDUnreachable:
        return None

    if not result.get("references"):
        return None

    citation_list_xml = build_xml.to_citation_list_xml(result, include_comment=False)
    _cache(article, citation_list_xml, "tier3", len(result["references"]))
    return citation_list_xml


def _cache(article, citation_list_xml: str, tier: str, refs_count: int) -> None:
    """Upsert a ParsedReferenceList row for this article."""
    requires_review = tier in {"tier2", "tier3"}
    ParsedReferenceList.objects.update_or_create(
        article=article,
        defaults={
            "citation_list_xml": citation_list_xml,
            "tier": tier,
            "references_count": refs_count,
            "requires_review": requires_review,
        },
    )
