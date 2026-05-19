"""
Tier detection. Routes a galley to the right extractor.

Plugin context: providers call `detect_tier_from_html(html_str)` with
the galley content already in memory. The path-based wrapper is kept
for parity with the Poroi sandbox CLI scripts.
"""

from __future__ import annotations

from pathlib import Path


def detect_tier_from_html(html: str) -> str:
    """Return 'tier1', 'tier2', or 'unknown' based on content markers.

    Tier 1: structured <p class="ref"> paragraphs.
    Tier 2: footnoted <p class="endnotes"> with no Tier 1 markers.
    """
    if 'class="ref"' in html:
        return "tier1"
    if 'class="endnotes"' in html:
        return "tier2"
    return "unknown"


def detect_tier_from_path(path: Path) -> str:
    """Path-based detection used by the Poroi CLI sandbox.

    PDFs are always Tier 3; HTML files dispatch to content detection.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "tier3"
    if suffix not in {".htm", ".html"}:
        return "unknown"
    text = path.read_text(encoding="utf-8", errors="replace")
    return detect_tier_from_html(text)
