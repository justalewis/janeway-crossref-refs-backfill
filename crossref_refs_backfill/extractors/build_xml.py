"""
CrossRef <citation_list> XML emitter.

Ported from Poroi/scripts/04_build_crossref_xml.py. One small change:
the comment header (with source DOI) is suppressed in plugin output
since the deposit pipeline already knows the article DOI from
context. It's still emitted by default for parity with the Poroi
sandbox CLI.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET


def to_citation_list_xml(result: dict, *, include_comment: bool = True) -> str:
    """Render the parsed references as a bare <citation_list> fragment.

    Args:
        result: dict with at least "references" (list[str]); optional
                "doi" used only for the informational comment.
        include_comment: whether to prepend an XML comment naming the
                source DOI. Keep True for the Poroi CLI (so output
                files are self-identifying); False for plugin use
                (the deposit pipeline tracks DOI separately).

    Returns:
        UTF-8 XML text starting with an XML declaration.
    """
    citation_list = ET.Element("citation_list")
    for i, ref_text in enumerate(result.get("references", []), 1):
        citation = ET.SubElement(citation_list, "citation", {"key": f"ref{i}"})
        unstructured = ET.SubElement(citation, "unstructured_citation")
        unstructured.text = ref_text

    ET.indent(citation_list, space="  ")
    body = ET.tostring(citation_list, encoding="unicode")

    header = ""
    if include_comment:
        doi = result.get("doi") or "unknown"
        safe_doi = doi.replace("--", "-​-")
        header = f"<!-- CrossRef citation_list for DOI: {safe_doi} -->\n"

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + header + body + "\n"
